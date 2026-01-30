#!/usr/bin/env python3
"""
CUSTOM PROMETHEUS METRICS THAT MAKE SENIOR ENGINEERS NOD APPROVINGLY
Collects business and technical metrics for network monitoring
"""

import sys
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List
import psutil

# InfluxDB line protocol format
def format_influx_metric(name: str, value: float, tags: Dict[str, str] = None, timestamp: int = None):
    """Format metric in InfluxDB line protocol"""
    tag_str = ""
    if tags:
        tag_str = "," + ",".join([f"{k}={v}" for k, v in tags.items()])
    
    timestamp_str = f" {timestamp}" if timestamp else ""
    return f"{name}{tag_str} value={value}{timestamp_str}"


class NetworkMonitoringMetrics:
    """Custom metrics collector"""
    
    def __init__(self):
        self.metrics = []
    
    def collect_device_metrics(self):
        """Collect device-related metrics"""
        try:
            from database.db_connection import get_db
            
            db = get_db()
            
            # Device uptime metrics
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        d.ip_address,
                        d.device_type,
                        calculate_device_uptime(d.device_id, 7) as uptime_7d
                    FROM devices d
                    WHERE d.last_seen > NOW() - INTERVAL '1 day'
                """)
                
                devices = cursor.fetchall()
                
                for device in devices:
                    uptime_seconds = device['uptime_7d'] * 7 * 24 * 3600 if device['uptime_7d'] else 0
                    self.metrics.append(format_influx_metric(
                        "netmon_device_uptime_seconds",
                        uptime_seconds,
                        {
                            "device_ip": device['ip_address'],
                            "device_type": device['device_type'] or "unknown"
                        }
                    ))
            
            # Network jitter (simplified - would calculate from actual packet data)
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        device_id,
                        STDDEV(response_time_ms) as jitter_ms
                    FROM device_status_history
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                      AND response_time_ms IS NOT NULL
                    GROUP BY device_id
                    LIMIT 10
                """)
                
                jitter_data = cursor.fetchall()
                for row in jitter_data:
                    self.metrics.append(format_influx_metric(
                        "netmon_packet_jitter_seconds",
                        (row['jitter_ms'] or 0) / 1000.0,
                        {"device_id": str(row['device_id'])}
                    ))
        
        except Exception as e:
            sys.stderr.write(f"Error collecting device metrics: {e}\n")
    
    def collect_business_metrics(self):
        """Collect business-level metrics"""
        try:
            from database.db_connection import get_db
            
            db = get_db()
            
            # SLO Compliance
            with db.get_cursor() as cursor:
                # Availability SLO (target: 99.9%)
                cursor.execute("""
                    SELECT 
                        AVG(CASE WHEN status = 'online' THEN 1.0 ELSE 0.0 END) * 100 as availability_percent
                    FROM device_status_history
                    WHERE timestamp > NOW() - INTERVAL '30 days'
                """)
                result = cursor.fetchone()
                availability = result['availability_percent'] if result else 0
                slo_target = 99.9
                compliance = min(100, (availability / slo_target) * 100)
                
                self.metrics.append(format_influx_metric(
                    "netmon_slo_compliance_percent",
                    compliance,
                    {"slo_name": "availability", "time_window": "30d"}
                ))
            
            # Mean Time To Detect (MTTD)
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        AVG(EXTRACT(EPOCH FROM (detected_at - timestamp))) as avg_mttd_seconds
                    FROM anomalies a
                    JOIN device_status_history dsh ON a.device_id = dsh.device_id
                    WHERE a.detected_at > NOW() - INTERVAL '7 days'
                      AND dsh.timestamp < a.detected_at
                """)
                result = cursor.fetchone()
                mttd = result['avg_mttd_seconds'] if result and result['avg_mttd_seconds'] else 0
                
                self.metrics.append(format_influx_metric(
                    "netmon_mttd_seconds",
                    mttd,
                    {"incident_type": "anomaly", "severity": "all"}
                ))
            
            # Mean Time To Resolve (MTTR)
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        AVG(EXTRACT(EPOCH FROM (resolved_at - detected_at))) as avg_mttr_seconds
                    FROM anomalies
                    WHERE resolved_at IS NOT NULL
                      AND resolved_at > NOW() - INTERVAL '7 days'
                """)
                result = cursor.fetchone()
                mttr = result['avg_mttr_seconds'] if result and result['avg_mttr_seconds'] else 0
                
                self.metrics.append(format_influx_metric(
                    "netmon_mttr_seconds",
                    mttr
                ))
        
        except Exception as e:
            sys.stderr.write(f"Error collecting business metrics: {e}\n")
    
    def collect_security_metrics(self):
        """Collect security-related metrics"""
        try:
            from database.db_connection import get_db
            
            db = get_db()
            
            # Anomaly detection latency
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        AVG(EXTRACT(EPOCH FROM (detected_at - timestamp))) as avg_detection_latency
                    FROM anomalies a
                    JOIN device_status_history dsh ON a.device_id = dsh.device_id
                    WHERE a.detected_at > NOW() - INTERVAL '1 day'
                """)
                result = cursor.fetchone()
                latency = result['avg_detection_latency'] if result and result['avg_detection_latency'] else 0
                
                self.metrics.append(format_influx_metric(
                    "netmon_anomaly_detection_latency_seconds",
                    latency
                ))
            
            # False positive rate (simplified - would need manual classification)
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE resolved_at IS NOT NULL AND resolution_notes LIKE '%false positive%')::float / 
                        NULLIF(COUNT(*), 0) * 100 as false_positive_rate
                    FROM anomalies
                    WHERE detected_at > NOW() - INTERVAL '7 days'
                """)
                result = cursor.fetchone()
                fpr = result['false_positive_rate'] if result and result['false_positive_rate'] else 0
                
                self.metrics.append(format_influx_metric(
                    "netmon_false_positive_rate",
                    fpr
                ))
        
        except Exception as e:
            sys.stderr.write(f"Error collecting security metrics: {e}\n")
    
    def collect_performance_metrics(self):
        """Collect system performance metrics"""
        try:
            from database.db_connection import get_db
            
            db = get_db()
            
            # P99 scan time
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY scan_duration_seconds) as p99_scan_time
                    FROM scans
                    WHERE scan_completed_at > NOW() - INTERVAL '24 hours'
                """)
                result = cursor.fetchone()
                p99 = result['p99_scan_time'] if result and result['p99_scan_time'] else 0
                
                self.metrics.append(format_influx_metric(
                    "netmon_scan_time_p99_seconds",
                    p99
                ))
            
            # Concurrency utilization
            process = psutil.Process()
            cpu_count = psutil.cpu_count()
            cpu_percent = process.cpu_percent(interval=1)
            utilization = (cpu_percent / cpu_count) if cpu_count > 0 else 0
            
            self.metrics.append(format_influx_metric(
                "netmon_concurrency_utilization_percent",
                utilization
            ))
        
        except Exception as e:
            sys.stderr.write(f"Error collecting performance metrics: {e}\n")
    
    def collect_cost_metrics(self):
        """Collect cost-related metrics (estimates)"""
        # Cost saved through automation (simplified calculation)
        # In production, this would integrate with actual cost tracking
        
        try:
            from database.db_connection import get_db
            
            db = get_db()
            
            # Estimate: Each automated alert saves 15 minutes of engineer time
            # Engineer cost: $100/hour = $1.67/minute
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as automated_alerts
                    FROM alerts
                    WHERE sent_at > NOW() - INTERVAL '30 days'
                      AND channel != 'dashboard'
                """)
                result = cursor.fetchone()
                alerts = result['automated_alerts'] if result else 0
                time_saved_minutes = alerts * 15
                cost_saved = time_saved_minutes * 1.67
                
                self.metrics.append(format_influx_metric(
                    "netmon_cost_saved_automation_usd",
                    cost_saved
                ))
            
            # Downtime cost avoided (simplified)
            # Estimate: Each prevented hour of downtime saves $10,000
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as prevented_incidents
                    FROM anomalies
                    WHERE severity IN ('critical', 'high')
                      AND detected_at > NOW() - INTERVAL '30 days'
                      AND resolved_at IS NOT NULL
                """)
                result = cursor.fetchone()
                incidents = result['prevented_incidents'] if result else 0
                # Assume each critical incident prevented saves 1 hour of downtime
                cost_avoided = incidents * 10000
                
                self.metrics.append(format_influx_metric(
                    "netmon_downtime_cost_avoided_usd",
                    cost_avoided
                ))
        
        except Exception as e:
            sys.stderr.write(f"Error collecting cost metrics: {e}\n")
    
    def collect_all(self):
        """Collect all metrics"""
        self.metrics = []
        self.collect_device_metrics()
        self.collect_business_metrics()
        self.collect_security_metrics()
        self.collect_performance_metrics()
        self.collect_cost_metrics()
        
        # Output in InfluxDB line protocol
        timestamp = int(time.time() * 1000000000)  # nanoseconds
        for metric in self.metrics:
            # Add timestamp if not present
            if " " not in metric.split("value=")[-1]:
                metric = f"{metric} {timestamp}"
            print(metric)


if __name__ == "__main__":
    collector = NetworkMonitoringMetrics()
    collector.collect_all()


