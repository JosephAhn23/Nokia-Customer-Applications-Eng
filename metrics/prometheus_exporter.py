"""
Prometheus Metrics Exporter
Exposes custom metrics via Prometheus format
"""

from prometheus_client import (
    Gauge, Histogram, Counter, Info, 
    generate_latest, REGISTRY, start_http_server
)
import asyncio
import psutil
import time
from datetime import datetime
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class NetworkMonitoringMetrics:
    """Prometheus metrics for network monitoring"""
    
    def __init__(self):
        # Network Health Metrics
        self.device_uptime = Gauge(
            'netmon_device_uptime_seconds',
            'Device uptime in seconds',
            ['device_ip', 'device_type']
        )
        
        self.network_jitter = Histogram(
            'netmon_packet_jitter_seconds',
            'Network packet jitter distribution',
            ['source', 'destination'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
        )
        
        self.tcp_connection_states = Gauge(
            'netmon_tcp_connections_total',
            'TCP connections by state',
            ['state']
        )
        
        # Business Metrics
        self.service_level_objectives = Gauge(
            'netmon_slo_compliance_percent',
            'Service Level Objective compliance percentage',
            ['slo_name', 'time_window']
        )
        
        self.mean_time_to_detect = Gauge(
            'netmon_mttd_seconds',
            'Mean Time To Detect incidents',
            ['incident_type', 'severity']
        )
        
        self.mean_time_to_resolve = Gauge(
            'netmon_mttr_seconds',
            'Mean Time To Resolve incidents'
        )
        
        # Security Metrics
        self.anomaly_detection_latency = Histogram(
            'netmon_anomaly_detection_latency_seconds',
            'Time from anomaly occurrence to detection',
            buckets=[0.1, 0.5, 1, 5, 10, 30, 60]
        )
        
        self.false_positive_rate = Gauge(
            'netmon_false_positive_rate',
            'False positive rate for anomaly detection'
        )
        
        # System Performance Metrics
        self.p99_scan_time = Gauge(
            'netmon_scan_time_p99_seconds',
            '99th percentile network scan duration'
        )
        
        self.concurrency_utilization = Gauge(
            'netmon_concurrency_utilization_percent',
            'Percentage of available concurrency being used'
        )
        
        # Cost Metrics
        self.cost_saved_automation = Counter(
            'netmon_cost_saved_automation_usd',
            'Estimated cost saved through automation'
        )
        
        self.downtime_cost_avoided = Counter(
            'netmon_downtime_cost_avoided_usd',
            'Estimated downtime cost avoided through early detection'
        )
        
        # Predictive Metrics
        self.forecast_accuracy = Gauge(
            'netmon_forecast_accuracy_percent',
            'Accuracy of predictive forecasts vs actuals'
        )
        
        self.predicted_disk_exhaustion_days = Gauge(
            'netmon_predicted_disk_exhaustion_days',
            'Predicted days until disk is full'
        )
    
    async def update_metrics(self):
        """Update all metrics from database"""
        try:
            from database.db_connection import get_db
            
            db = get_db()
            
            # Update device uptime
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        d.ip_address,
                        d.device_type,
                        calculate_device_uptime(d.device_id, 7) * 7 * 24 * 3600 as uptime_seconds
                    FROM devices d
                    WHERE d.last_seen > NOW() - INTERVAL '1 day'
                """)
                
                for device in cursor.fetchall():
                    self.device_uptime.labels(
                        device_ip=device['ip_address'],
                        device_type=device['device_type'] or 'unknown'
                    ).set(device['uptime_seconds'] or 0)
            
            # Update SLO compliance
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        AVG(CASE WHEN status = 'online' THEN 1.0 ELSE 0.0 END) * 100 as availability
                    FROM device_status_history
                    WHERE timestamp > NOW() - INTERVAL '30 days'
                """)
                result = cursor.fetchone()
                availability = result['availability'] if result else 0
                compliance = min(100, (availability / 99.9) * 100)
                
                self.service_level_objectives.labels(
                    slo_name='availability',
                    time_window='30d'
                ).set(compliance)
            
            # Update MTTD
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        AVG(EXTRACT(EPOCH FROM (detected_at - timestamp))) as mttd
                    FROM anomalies a
                    JOIN device_status_history dsh ON a.device_id = dsh.device_id
                    WHERE a.detected_at > NOW() - INTERVAL '7 days'
                """)
                result = cursor.fetchone()
                mttd = result['mttd'] if result and result['mttd'] else 0
                
                self.mean_time_to_detect.labels(
                    incident_type='anomaly',
                    severity='all'
                ).set(mttd)
            
            # Update MTTR
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        AVG(EXTRACT(EPOCH FROM (resolved_at - detected_at))) as mttr
                    FROM anomalies
                    WHERE resolved_at IS NOT NULL
                      AND resolved_at > NOW() - INTERVAL '7 days'
                """)
                result = cursor.fetchone()
                mttr = result['mttr'] if result and result['mttr'] else 0
                
                self.mean_time_to_resolve.set(mttr)
            
            # Update P99 scan time
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY scan_duration_seconds) as p99
                    FROM scans
                    WHERE scan_completed_at > NOW() - INTERVAL '24 hours'
                """)
                result = cursor.fetchone()
                p99 = result['p99'] if result and result['p99'] else 0
                
                self.p99_scan_time.set(p99)
            
            # Update concurrency utilization
            process = psutil.Process()
            cpu_count = psutil.cpu_count()
            cpu_percent = process.cpu_percent(interval=0.1)
            utilization = (cpu_percent / cpu_count) if cpu_count > 0 else 0
            
            self.concurrency_utilization.set(utilization)
            
            # Update TCP connection states
            connections = psutil.net_connections(kind='tcp')
            states = {}
            for conn in connections:
                state = conn.status
                states[state] = states.get(state, 0) + 1
            
            for state, count in states.items():
                self.tcp_connection_states.labels(state=state).set(count)
            
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
    
    async def run(self, port: int = 9090):
        """Start Prometheus metrics server"""
        start_http_server(port)
        logger.info(f"Prometheus metrics server started on port {port}")
        
        while True:
            await self.update_metrics()
            await asyncio.sleep(30)  # Update every 30 seconds


if __name__ == "__main__":
    metrics = NetworkMonitoringMetrics()
    asyncio.run(metrics.run())


