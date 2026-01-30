"""
Network Monitor Data Processing Pipeline
Three-stage processing: Validation -> Enrichment -> Analysis
"""

import asyncio
import json
import logging
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ProcessedResult:
    """Result of processing a scan"""
    enriched_devices: List[Dict]
    analysis: Dict
    timestamp: str


class InvalidScanError(Exception):
    """Raised when scan data fails validation"""
    pass


class CircuitBreaker:
    """Circuit breaker pattern for external lookups"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "half_open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True
        
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.timeout


class DeviceProcessor:
    """Main device processing class"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.known_devices: Dict[str, Dict] = {}
        self.baseline_metrics: Dict[str, Dict] = {}
        self.previous_ports: Dict[str, Set[int]] = {}
        self.device_uptime: Dict[str, float] = {}
        self.circuit_breaker = CircuitBreaker()
        
        # Load historical data
        self._load_known_devices()
        self._establish_baseline()
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return {}
    
    def _load_known_devices(self):
        """Load known devices from database or cache"""
        # This would typically load from database
        # For now, we'll use a simple file-based cache
        cache_file = Path(__file__).parent.parent / "data" / "known_devices.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    self.known_devices = {d['ip']: d for d in data.get('devices', [])}
                    logger.info(f"Loaded {len(self.known_devices)} known devices")
            except Exception as e:
                logger.error(f"Error loading known devices: {e}")
    
    def _establish_baseline(self):
        """Establish baseline metrics for devices"""
        baseline_window = self.config.get('processing', {}).get('baseline_window_days', 7)
        
        # This would typically query the database for historical data
        # For now, we'll calculate from known devices
        for ip, device in self.known_devices.items():
            if 'response_time_ms' in device:
                self.baseline_metrics[ip] = {
                    'avg_rtt': device.get('response_time_ms', 0),
                    'std_dev': 0,  # Would calculate from history
                    'uptime': device.get('uptime', 0.95)
                }
    
    def _validate_scan(self, scan_data: Dict) -> bool:
        """Stage 1: Validation - Sanity check incoming data"""
        try:
            # Check required fields
            if 'scan_id' not in scan_data:
                logger.error("Missing scan_id in scan data")
                return False
            
            if 'subnet' not in scan_data:
                logger.error("Missing subnet in scan data")
                return False
            
            if 'devices' not in scan_data:
                logger.error("Missing devices array in scan data")
                return False
            
            # Validate devices array
            if not isinstance(scan_data['devices'], list):
                logger.error("devices must be an array")
                return False
            
            # Validate each device
            for device in scan_data['devices']:
                if 'ip' not in device:
                    logger.error("Device missing IP address")
                    return False
                
                # Validate IP format (basic check)
                ip = device['ip']
                parts = ip.split('.')
                if len(parts) != 4:
                    logger.error(f"Invalid IP format: {ip}")
                    return False
                
                for part in parts:
                    if not part.isdigit() or int(part) > 255:
                        logger.error(f"Invalid IP octet: {part}")
                        return False
            
            logger.info(f"Validation passed for scan {scan_data['scan_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def _enrich_devices(self, devices: List[Dict]) -> List[Dict]:
        """Stage 2: Enrichment - Add contextual information"""
        enriched = []
        
        for device in devices:
            enriched_device = device.copy()
            
            # Add device classification
            enriched_device['device_type'] = self._classify_device(device)
            
            # Add risk score
            enriched_device['risk_score'] = self._calculate_risk_score(device)
            
            # Add network segment (if available)
            if 'subnet' in device:
                enriched_device['network_segment'] = device['subnet']
            
            # Add first seen timestamp if new device
            if device['ip'] not in self.known_devices:
                enriched_device['first_seen'] = datetime.utcnow().isoformat()
            else:
                enriched_device['first_seen'] = self.known_devices[device['ip']].get('first_seen')
            
            enriched.append(enriched_device)
        
        return enriched
    
    def _classify_device(self, device: Dict) -> str:
        """Classify device type based on characteristics"""
        vendor = device.get('vendor', '').lower()
        os_family = device.get('os_family', '').lower()
        ports = set(device.get('open_ports', []))
        
        # Router/Gateway detection
        if any(keyword in vendor for keyword in ['cisco', 'juniper', 'arista', 'router']):
            return 'router'
        
        # Server detection
        if 22 in ports and (80 in ports or 443 in ports):
            return 'server'
        
        # Printer detection
        if 9100 in ports or 'printer' in vendor.lower():
            return 'printer'
        
        # IoT device
        if len(ports) == 0 or len(ports) == 1:
            return 'iot_device'
        
        return 'unknown'
    
    def _calculate_risk_score(self, device: Dict) -> float:
        """Calculate risk score (0-100) for device"""
        score = 0.0
        
        # Open ports increase risk
        open_ports = device.get('open_ports', [])
        score += len(open_ports) * 2
        
        # High-risk ports
        high_risk_ports = [21, 23, 135, 139, 445, 1433, 3306, 5432, 3389]
        for port in open_ports:
            if port in high_risk_ports:
                score += 10
        
        # Unknown device
        if device['ip'] not in self.known_devices:
            score += 5
        
        # No vendor information
        if not device.get('vendor'):
            score += 3
        
        return min(score, 100.0)
    
    def _get_previous_ports(self, ip: str) -> Set[int]:
        """Get previous open ports for device"""
        return self.previous_ports.get(ip, set())
    
    def _calculate_uptime(self, ip: str) -> float:
        """Calculate device uptime percentage"""
        return self.device_uptime.get(ip, 0.95)
    
    def _analyze_changes(self, devices: List[Dict]) -> Dict:
        """Stage 3: Analysis - Detect anomalies and changes"""
        anomalies = []
        
        for device in devices:
            ip = device['ip']
            status = device.get('status', 'offline')
            
            # CHECK 1: Sudden disappearance
            if ip in self.known_devices and status == 'offline':
                uptime = self._calculate_uptime(ip)
                uptime_threshold = self.config.get('processing', {}).get('uptime_threshold_for_downtime_alert', 0.95)
                
                if uptime > uptime_threshold:
                    anomalies.append({
                        'type': 'sudden_downtime',
                        'device': ip,
                        'device_name': device.get('hostname', ip),
                        'severity': 'high',
                        'confidence': 0.89,
                        'previous_uptime': uptime,
                        'timestamp': datetime.utcnow().isoformat()
                    })
            
            # CHECK 2: Port changes (security concern)
            current_ports = set(device.get('open_ports', []))
            previous_ports = self._get_previous_ports(ip)
            
            new_ports = current_ports - previous_ports
            closed_ports = previous_ports - current_ports
            
            if new_ports:
                # Check against whitelist
                whitelist = self.config.get('alerting', {}).get('rules', {}).get('new_ports_opened', {}).get('whitelist_ports', [])
                suspicious_ports = [p for p in new_ports if p not in whitelist]
                
                if suspicious_ports:
                    anomalies.append({
                        'type': 'new_ports_opened',
                        'device': ip,
                        'device_name': device.get('hostname', ip),
                        'ports': list(suspicious_ports),
                        'all_new_ports': list(new_ports),
                        'severity': 'medium',
                        'confidence': 0.95,
                        'timestamp': datetime.utcnow().isoformat()
                    })
            
            if closed_ports and status == 'online':
                anomalies.append({
                    'type': 'ports_closed',
                    'device': ip,
                    'device_name': device.get('hostname', ip),
                    'ports': list(closed_ports),
                    'severity': 'low',
                    'confidence': 0.85,
                    'timestamp': datetime.utcnow().isoformat()
                })
            
            # CHECK 3: Response time degradation
            if status == 'online':
                current_rtt = device.get('response_time_ms', 0)
                baseline = self.baseline_metrics.get(ip, {})
                baseline_rtt = baseline.get('avg_rtt', 0)
                
                threshold_multiplier = self.config.get('processing', {}).get('latency_spike_threshold_multiplier', 2.5)
                
                if baseline_rtt > 0 and current_rtt > baseline_rtt * threshold_multiplier:
                    increase_percent = ((current_rtt - baseline_rtt) / baseline_rtt) * 100
                    anomalies.append({
                        'type': 'latency_spike',
                        'device': ip,
                        'device_name': device.get('hostname', ip),
                        'current': current_rtt,
                        'baseline': baseline_rtt,
                        'increase_percent': round(increase_percent, 2),
                        'severity': 'low',
                        'confidence': 0.75,
                        'timestamp': datetime.utcnow().isoformat()
                    })
            
            # CHECK 4: New device detected
            if ip not in self.known_devices and status == 'online':
                anomalies.append({
                    'type': 'new_device',
                    'device': ip,
                    'device_name': device.get('hostname', ip),
                    'mac': device.get('mac', ''),
                    'vendor': device.get('vendor', ''),
                    'severity': 'medium',
                    'confidence': 1.0,
                    'timestamp': datetime.utcnow().isoformat()
                })
            
            # Update previous ports
            if status == 'online':
                self.previous_ports[ip] = current_ports
        
        # Calculate summary statistics
        summary_stats = self._calculate_summary_stats(devices)
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'anomalies_detected': len(anomalies),
            'anomalies': anomalies,
            'summary_stats': summary_stats
        }
    
    def _calculate_summary_stats(self, devices: List[Dict]) -> Dict:
        """Calculate summary statistics"""
        online_devices = [d for d in devices if d.get('status') == 'online']
        offline_devices = [d for d in devices if d.get('status') == 'offline']
        
        response_times = [d.get('response_time_ms', 0) for d in online_devices if d.get('response_time_ms', 0) > 0]
        
        stats = {
            'total_devices': len(devices),
            'online_count': len(online_devices),
            'offline_count': len(offline_devices),
            'availability_percent': round((len(online_devices) / len(devices) * 100) if devices else 0, 2)
        }
        
        if response_times:
            stats['avg_response_time_ms'] = round(statistics.mean(response_times), 2)
            stats['min_response_time_ms'] = round(min(response_times), 2)
            stats['max_response_time_ms'] = round(max(response_times), 2)
            if len(response_times) > 1:
                stats['std_dev_response_time_ms'] = round(statistics.stdev(response_times), 2)
        
        return stats
    
    def _store_results(self, enriched_devices: List[Dict], analysis: Dict):
        """Store processing results"""
        # Update known devices
        for device in enriched_devices:
            self.known_devices[device['ip']] = device
        
        # Save to cache
        cache_file = Path(__file__).parent.parent / "data" / "known_devices.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(cache_file, 'w') as f:
            json.dump({
                'last_updated': datetime.utcnow().isoformat(),
                'devices': list(self.known_devices.values())
            }, f, indent=2)
    
    async def process_scan_async(self, scan_data: Dict) -> ProcessedResult:
        """Async version of process_scan"""
        return await asyncio.to_thread(self.process_scan, scan_data)
    
    def process_scan(self, scan_data: Dict) -> ProcessedResult:
        """Main processing entry point"""
        # 1. VALIDATION
        if not self._validate_scan(scan_data):
            raise InvalidScanError("Scan data failed validation")
        
        # 2. ENRICHMENT
        enriched = self._enrich_devices(scan_data['devices'])
        
        # 3. ANALYSIS
        analysis = self._analyze_changes(enriched)
        
        # 4. PERSISTENCE
        self._store_results(enriched, analysis)
        
        return ProcessedResult(
            enriched_devices=enriched,
            analysis=analysis,
            timestamp=datetime.utcnow().isoformat()
        )


# Main entry point for CLI usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: pipeline.py <scan_json_file>")
        sys.exit(1)
    
    scan_file = Path(sys.argv[1])
    if not scan_file.exists():
        print(f"Error: File not found: {scan_file}")
        sys.exit(1)
    
    with open(scan_file, 'r') as f:
        scan_data = json.load(f)
    
    processor = DeviceProcessor()
    result = processor.process_scan(scan_data)
    
    print(json.dumps({
        'enriched_devices': result.enriched_devices,
        'analysis': result.analysis
    }, indent=2))


