"""
Main entry point for the alerting service
Continuously monitors for new anomalies and sends alerts
"""

import asyncio
import logging
import time
from datetime import datetime

from alerter.engine import AlertEngine
from database.db_connection import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def process_pending_alerts():
    """Process pending alerts from database"""
    alerter = AlertEngine()
    db = get_db()
    
    while True:
        try:
            # Get unprocessed anomalies
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        a.anomaly_id,
                        a.device_id,
                        a.anomaly_type,
                        a.severity,
                        a.description,
                        a.confidence,
                        a.metadata,
                        a.detected_at,
                        d.ip_address,
                        d.hostname
                    FROM anomalies a
                    LEFT JOIN devices d ON a.device_id = d.device_id
                    WHERE a.resolved_at IS NULL
                      AND a.detected_at >= NOW() - INTERVAL '1 hour'
                      AND NOT EXISTS (
                          SELECT 1 FROM alerts 
                          WHERE alerts.anomaly_id = a.anomaly_id
                      )
                    ORDER BY a.detected_at DESC
                    LIMIT 10
                """)
                anomalies = cursor.fetchall()
            
            if anomalies:
                # Convert to dict format expected by alerter
                anomaly_list = []
                for anom in anomalies:
                    anomaly_dict = {
                        'anomaly_id': anom['anomaly_id'],
                        'type': anom['anomaly_type'],
                        'severity': anom['severity'],
                        'description': anom['description'],
                        'confidence': float(anom['confidence']) if anom['confidence'] else None,
                        'device': anom['ip_address'],
                        'device_name': anom['hostname'],
                        'timestamp': anom['detected_at'].isoformat() if anom['detected_at'] else None
                    }
                    
                    # Parse metadata if available
                    if anom.get('metadata'):
                        import json
                        try:
                            metadata = json.loads(anom['metadata']) if isinstance(anom['metadata'], str) else anom['metadata']
                            anomaly_dict.update(metadata)
                        except:
                            pass
                    
                    anomaly_list.append(anomaly_dict)
                
                if anomaly_list:
                    await alerter.process_anomalies(anomaly_list)
                    logger.info(f"Processed {len(anomaly_list)} anomalies for alerting")
        
        except Exception as e:
            logger.error(f"Error processing alerts: {e}")
        
        # Wait before next check
        await asyncio.sleep(30)


def main():
    """Main alerting loop"""
    logger.info("Starting Network Monitor Alerting Service")
    
    try:
        asyncio.run(process_pending_alerts())
    except KeyboardInterrupt:
        logger.info("Shutting down alerter")


if __name__ == "__main__":
    main()


