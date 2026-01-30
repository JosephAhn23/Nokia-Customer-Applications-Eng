"""
PROACTIVE MEMORY LEAK DETECTION WITH AUTOMATED RECOVERY
Advanced memory management monitor for long-running processes
"""

import psutil
import gc
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)


class LeakSeverity(Enum):
    NORMAL = "normal"
    SUSPICIOUS = "suspicious"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class MemoryProfile:
    rss_mb: float
    vms_mb: float
    shared_mb: float
    percent: float
    heap_objects: int
    gc_generation_counts: Dict[int, int]
    timestamp: datetime


class MemoryGuardian:
    """Memory leak detection and management system"""
    
    def __init__(self, process_name: str, alert_threshold_mb: float = 1000):
        self.process_name = process_name
        self.alert_threshold = alert_threshold_mb
        self.process = psutil.Process()
        
        # Leak detection configuration
        self.sampling_interval = 60  # seconds
        self.training_period = 24 * 3600  # 24 hours
        self.min_samples_for_baseline = 100
        
        # Statistical models
        self.memory_baseline = None
        self.growth_model = None
        
        # Tracking
        self.history: List[MemoryProfile] = []
        self.leak_incidents = []
        self.recovery_actions = []
        
        # Monitoring control
        self.monitor_thread = None
        self.should_stop = threading.Event()
        self.is_monitoring = False
    
    def start_monitoring(self):
        """Start the monitoring thread"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"Memory Guardian started for {self.process_name}")
    
    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self.should_stop.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.is_monitoring = False
        logger.info(f"Memory Guardian stopped for {self.process_name}")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while not self.should_stop.wait(self.sampling_interval):
            try:
                profile = self._capture_memory_profile()
                self.history.append(profile)
                
                # Keep only last 1000 profiles
                if len(self.history) > 1000:
                    self.history = self.history[-1000:]
                
                # Analyze for leaks
                leak_analysis = self._analyze_for_leaks(profile)
                
                if leak_analysis['severity'] != LeakSeverity.NORMAL:
                    self._handle_memory_anomaly(profile, leak_analysis)
                
                # Periodic cleanup actions
                if len(self.history) % 10 == 0:  # Every 10 samples
                    self._perform_preventive_maintenance()
                    
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
    
    def _capture_memory_profile(self) -> MemoryProfile:
        """Comprehensive memory profiling"""
        gc.collect()  # Force garbage collection before measuring
        
        process_info = self.process.memory_info()
        
        # Get GC generation statistics
        gen_counts = {}
        gc_counts = gc.get_count()
        for i in range(len(gc_counts)):
            gen_counts[i] = gc_counts[i]
        
        return MemoryProfile(
            rss_mb=process_info.rss / 1024 / 1024,
            vms_mb=process_info.vms / 1024 / 1024,
            shared_mb=process_info.shared / 1024 / 1024,
            percent=self.process.memory_percent(),
            heap_objects=sum(gc_counts),
            gc_generation_counts=gen_counts,
            timestamp=datetime.utcnow()
        )
    
    def _analyze_for_leaks(self, profile: MemoryProfile) -> Dict[str, Any]:
        """Multi-method leak detection"""
        analysis = {
            'severity': LeakSeverity.NORMAL,
            'confidence': 0.0,
            'indicators': [],
            'estimated_leak_rate_mb_per_hour': 0.0
        }
        
        if len(self.history) < self.min_samples_for_baseline:
            return analysis
        
        recent_profiles = self.history[-50:]  # Last 50 samples
        
        # METHOD 1: LINEAR REGRESSION FOR TREND
        if len(recent_profiles) >= 10:
            times = [(p.timestamp - recent_profiles[0].timestamp).total_seconds() 
                    for p in recent_profiles]
            rss_values = [p.rss_mb for p in recent_profiles]
            
            # Calculate linear regression
            try:
                slope, intercept = np.polyfit(times, rss_values, 1)
                
                # Convert slope to MB per hour
                mb_per_hour = slope * 3600
                
                if mb_per_hour > 5.0:  # Growing more than 5MB/hour
                    analysis['indicators'].append({
                        'method': 'linear_regression',
                        'growth_rate_mb_per_hour': mb_per_hour,
                        'r_squared': self._calculate_r_squared(times, rss_values, slope, intercept)
                    })
                    analysis['estimated_leak_rate_mb_per_hour'] = mb_per_hour
                    
                    if mb_per_hour > 50:
                        analysis['severity'] = LeakSeverity.CRITICAL
                        analysis['confidence'] = 0.9
                    elif mb_per_hour > 20:
                        analysis['severity'] = LeakSeverity.SUSPICIOUS
                        analysis['confidence'] = 0.7
            except Exception as e:
                logger.warning(f"Linear regression failed: {e}")
        
        # METHOD 2: GC GENERATION ANALYSIS
        if len(self.history) > 1:
            current_gen_counts = profile.gc_generation_counts
            previous_profile = self.history[-2]
            previous_gen_counts = previous_profile.gc_generation_counts
            
            # Check for objects surviving multiple collections
            for gen in range(3):  # Python has 3 GC generations
                if gen in current_gen_counts and gen in previous_gen_counts:
                    growth = current_gen_counts[gen] - previous_gen_counts[gen]
                    if growth > 1000:  # More than 1000 new objects in generation
                        analysis['indicators'].append({
                            'method': 'gc_generation_growth',
                            'generation': gen,
                            'growth': growth
                        })
                        if analysis['severity'] == LeakSeverity.NORMAL:
                            analysis['severity'] = LeakSeverity.SUSPICIOUS
                            analysis['confidence'] = 0.6
        
        # METHOD 3: ABSOLUTE THRESHOLD CHECK
        if profile.rss_mb > self.alert_threshold:
            analysis['indicators'].append({
                'method': 'absolute_threshold',
                'current_mb': profile.rss_mb,
                'threshold_mb': self.alert_threshold
            })
            if profile.rss_mb > self.alert_threshold * 1.5:
                analysis['severity'] = LeakSeverity.EMERGENCY
                analysis['confidence'] = 1.0
            elif profile.rss_mb > self.alert_threshold * 1.2:
                analysis['severity'] = LeakSeverity.CRITICAL
                analysis['confidence'] = 0.9
        
        # METHOD 4: PERCENTAGE GROWTH
        if len(self.history) >= 20:
            baseline = self.history[0].rss_mb
            current = profile.rss_mb
            growth_percent = ((current - baseline) / baseline) * 100
            
            if growth_percent > 50:  # 50% growth
                analysis['indicators'].append({
                    'method': 'percentage_growth',
                    'growth_percent': growth_percent,
                    'baseline_mb': baseline,
                    'current_mb': current
                })
                if growth_percent > 100:
                    analysis['severity'] = LeakSeverity.CRITICAL
                    analysis['confidence'] = 0.95
        
        return analysis
    
    def _calculate_r_squared(self, x, y, slope, intercept):
        """Calculate R-squared for regression"""
        try:
            y_pred = [slope * xi + intercept for xi in x]
            ss_res = sum((yi - ypi) ** 2 for yi, ypi in zip(y, y_pred))
            ss_tot = sum((yi - np.mean(y)) ** 2 for yi in y)
            return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        except Exception:
            return 0
    
    def _handle_memory_anomaly(self, profile: MemoryProfile, analysis: Dict[str, Any]):
        """Handle detected memory anomalies"""
        severity = analysis['severity']
        
        logger.warning(f"Memory anomaly detected: {severity.value} - {profile.rss_mb:.2f} MB")
        
        # Log incident
        incident = {
            'timestamp': profile.timestamp.isoformat(),
            'severity': severity.value,
            'rss_mb': profile.rss_mb,
            'analysis': analysis
        }
        self.leak_incidents.append(incident)
        
        # Take recovery actions based on severity
        if severity == LeakSeverity.EMERGENCY:
            self._emergency_recovery(profile)
        elif severity == LeakSeverity.CRITICAL:
            self._critical_recovery(profile)
        elif severity == LeakSeverity.SUSPICIOUS:
            self._suspicious_recovery(profile)
    
    def _emergency_recovery(self, profile: MemoryProfile):
        """Emergency memory recovery actions"""
        logger.critical("EMERGENCY: Initiating aggressive memory recovery")
        
        # Force multiple GC cycles
        for _ in range(3):
            gc.collect()
        
        # Alert administrators
        self._send_alert("EMERGENCY", f"Memory usage: {profile.rss_mb:.2f} MB")
        
        # Consider process restart if available
        logger.warning("Consider restarting process if memory continues to grow")
    
    def _critical_recovery(self, profile: MemoryProfile):
        """Critical memory recovery actions"""
        logger.warning("CRITICAL: Initiating memory recovery")
        
        # Force GC
        gc.collect()
        
        # Alert administrators
        self._send_alert("CRITICAL", f"Memory usage: {profile.rss_mb:.2f} MB")
    
    def _suspicious_recovery(self, profile: MemoryProfile):
        """Suspicious memory recovery actions"""
        logger.info("SUSPICIOUS: Monitoring memory growth")
        
        # Light GC
        gc.collect()
        
        # Log for analysis
        self._log_memory_event("suspicious_growth", profile)
    
    def _perform_preventive_maintenance(self):
        """Perform preventive memory maintenance"""
        # Periodic garbage collection
        collected = gc.collect()
        if collected > 0:
            logger.debug(f"Preventive GC collected {collected} objects")
    
    def _send_alert(self, severity: str, message: str):
        """Send memory alert"""
        try:
            from alerter.engine import AlertEngine
            import asyncio
            
            alerter = AlertEngine()
            anomaly = {
                'type': 'memory_leak',
                'device': self.process_name,
                'severity': severity.lower(),
                'description': f"Memory leak detected: {message}",
                'timestamp': datetime.utcnow().isoformat()
            }
            asyncio.run(alerter.process_anomalies([anomaly]))
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def _log_memory_event(self, event_type: str, profile: MemoryProfile):
        """Log memory event to database"""
        try:
            from database.db_connection import get_db
            
            db = get_db()
            with db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO memory_events (
                        process_name, event_type, rss_mb, details, created_at
                    ) VALUES (%s, %s, %s, %s, NOW())
                """, (
                    self.process_name,
                    event_type,
                    profile.rss_mb,
                    json.dumps({
                        'vms_mb': profile.vms_mb,
                        'percent': profile.percent,
                        'heap_objects': profile.heap_objects
                    })
                ))
        except Exception as e:
            logger.error(f"Failed to log memory event: {e}")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get current memory statistics"""
        if not self.history:
            return {}
        
        recent = self.history[-10:] if len(self.history) >= 10 else self.history
        
        return {
            'current_mb': recent[-1].rss_mb if recent else 0,
            'avg_mb': np.mean([p.rss_mb for p in recent]) if recent else 0,
            'max_mb': max([p.rss_mb for p in self.history]) if self.history else 0,
            'min_mb': min([p.rss_mb for p in self.history]) if self.history else 0,
            'leak_incidents': len(self.leak_incidents),
            'monitoring_duration_hours': (datetime.utcnow() - self.history[0].timestamp).total_seconds() / 3600 if self.history else 0
        }


# Global instance
_guardian_instance: Optional[MemoryGuardian] = None


def get_memory_guardian(process_name: str = "netmon") -> MemoryGuardian:
    """Get or create global memory guardian instance"""
    global _guardian_instance
    if _guardian_instance is None:
        _guardian_instance = MemoryGuardian(process_name)
        _guardian_instance.start_monitoring()
    return _guardian_instance


