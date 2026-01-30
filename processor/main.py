"""
Main entry point for the data processing service
Continuously processes scan results from the discovery service
"""

import asyncio
import json
import logging
import time
from pathlib import Path
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = None
    FileSystemEventHandler = None
    logger.warning("watchdog not installed, file watching disabled")

from processor.pipeline import DeviceProcessor
from alerter.engine import AlertEngine
from database.db_connection import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScanFileHandler(FileSystemEventHandler):
    """Watch for new scan files and process them"""
    
    def __init__(self, processor: DeviceProcessor, alerter: AlertEngine):
        self.processor = processor
        self.alerter = alerter
        self.processed_files = set()
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith('.json'):
            logger.info(f"New scan file detected: {event.src_path}")
            # Wait a moment for file to be fully written
            time.sleep(1)
            self.process_file(event.src_path)
    
    def process_file(self, file_path: str):
        """Process a scan file"""
        if file_path in self.processed_files:
            return
        
        try:
            with open(file_path, 'r') as f:
                scan_data = json.load(f)
            
            # Process scan
            result = self.processor.process_scan(scan_data)
            logger.info(f"Processed scan {scan_data.get('scan_id')}: {len(result.enriched_devices)} devices, {result.analysis['anomalies_detected']} anomalies")
            
            # Store in database
            self.store_to_database(result)
            
            # Process alerts
            if result.analysis['anomalies']:
                asyncio.run(self.alerter.process_anomalies(result.analysis['anomalies']))
            
            self.processed_files.add(file_path)
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
    
    def store_to_database(self, result):
        """Store processed results to database"""
        try:
            db = get_db()
            with db.get_cursor() as cursor:
                # Store devices and status history
                for device in result.enriched_devices:
                    # Insert or update device
                    cursor.execute("""
                        INSERT INTO devices (ip_address, mac_address, vendor, hostname, device_type, risk_score, last_seen)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ip_address, mac_address) 
                        DO UPDATE SET
                            vendor = EXCLUDED.vendor,
                            hostname = EXCLUDED.hostname,
                            device_type = EXCLUDED.device_type,
                            risk_score = EXCLUDED.risk_score,
                            last_seen = EXCLUDED.last_seen
                        RETURNING device_id
                    """, (
                        device['ip'],
                        device.get('mac'),
                        device.get('vendor'),
                        device.get('hostname'),
                        device.get('device_type'),
                        device.get('risk_score', 0),
                        device.get('last_seen')
                    ))
                    device_result = cursor.fetchone()
                    device_id = device_result['device_id']
                    
                    # Insert status history
                    cursor.execute("""
                        INSERT INTO device_status_history (device_id, status, response_time_ms, timestamp, scan_id)
                        VALUES (%s, %s, %s, %s, gen_random_uuid())
                    """, (
                        device_id,
                        device.get('status', 'offline'),
                        device.get('response_time_ms'),
                        device.get('last_seen')
                    ))
                    
                    # Store port scan results
                    if device.get('open_ports'):
                        cursor.execute("""
                            INSERT INTO port_scan_results (device_id, open_ports, scan_timestamp)
                            VALUES (%s, %s, NOW())
                        """, (device_id, device['open_ports']))
                
                # Store anomalies
                for anomaly in result.analysis.get('anomalies', []):
                    device_ip = anomaly.get('device')
                    device_id = None
                    if device_ip:
                        cursor.execute("SELECT device_id FROM devices WHERE ip_address = %s", (device_ip,))
                        device_result = cursor.fetchone()
                        if device_result:
                            device_id = device_result['device_id']
                    
                    cursor.execute("""
                        INSERT INTO anomalies (device_id, anomaly_type, severity, description, confidence, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        device_id,
                        anomaly.get('type'),
                        anomaly.get('severity'),
                        anomaly.get('description'),
                        anomaly.get('confidence'),
                        json.dumps(anomaly)
                    ))
            
            logger.info("Results stored to database")
        except Exception as e:
            logger.error(f"Error storing to database: {e}")


def main():
    """Main processing loop"""
    logger.info("Starting Network Monitor Data Processor")
    
    # Initialize components
    processor = DeviceProcessor()
    alerter = AlertEngine()
    
    # Watch for new scan files
    scan_dir = Path(__file__).parent.parent / "data" / "scans"
    scan_dir.mkdir(parents=True, exist_ok=True)
    
    event_handler = ScanFileHandler(processor, alerter)
    
    if Observer is not None:
        observer = Observer()
        observer.schedule(event_handler, str(scan_dir), recursive=False)
        observer.start()
        logger.info(f"Watching for scan files in {scan_dir}")
    else:
        observer = None
        logger.info(f"Polling for scan files in {scan_dir} (watchdog not available)")
    
    try:
        # Process any existing files
        for file_path in scan_dir.glob("*.json"):
            event_handler.process_file(str(file_path))
        
        # Keep running
        if observer:
            while True:
                time.sleep(1)
        else:
            # Polling mode if watchdog not available
            while True:
                # Check for new files every 10 seconds
                for file_path in scan_dir.glob("*.json"):
                    event_handler.process_file(str(file_path))
                time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Shutting down processor")
        if observer:
            observer.stop()
            observer.join()


if __name__ == "__main__":
    main()

