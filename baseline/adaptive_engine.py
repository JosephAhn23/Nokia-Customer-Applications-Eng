"""
INTELLIGENT BASELINE MANAGEMENT WITH CONCEPT DRIFT DETECTION
Adaptive baseline recalibration for network monitoring
"""

import numpy as np
from scipy import stats
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import json
import logging
from pathlib import Path

from database.db_connection import get_db

logger = logging.getLogger(__name__)


class BaselineState(Enum):
    STABLE = "stable"
    LEARNING = "learning"
    DRIFT_DETECTED = "drift_detected"
    RECALIBRATING = "recalibrating"
    DEGRADED = "degraded"


class AdaptiveBaseline:
    """Adaptive baseline engine with concept drift detection"""
    
    def __init__(self, device_ip: str, metric_type: str):
        self.device_ip = device_ip
        self.metric_type = metric_type  # 'response_time', 'packet_loss', 'throughput'
        self.state = BaselineState.LEARNING
        
        # Window configuration
        self.min_learning_samples = 100
        self.full_history_days = 30
        self.recent_window_hours = 24
        self.seasonal_periods = {
            'hourly': 24,
            'daily': 7,
            'weekly': 4
        }
        
        # Statistical models
        self.baseline_stats = None
        self.drift_confidence = 0.0
        
        # Load existing baseline
        self._load_baseline()
    
    def _load_baseline(self):
        """Load baseline from database"""
        try:
            db = get_db()
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT baseline_data
                    FROM device_baselines
                    WHERE device_ip = %s AND metric_type = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (self.device_ip, self.metric_type))
                
                result = cursor.fetchone()
                if result and result.get('baseline_data'):
                    self.baseline_stats = json.loads(result['baseline_data'])
                    self.state = BaselineState.STABLE
                    logger.info(f"Loaded baseline for {self.device_ip}/{self.metric_type}")
        except Exception as e:
            logger.warning(f"Could not load baseline: {e}")
            self.baseline_stats = None
    
    def should_recalibrate(self, recent_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Decision engine for baseline recalibration
        Returns: {
            'recalibrate': bool,
            'reason': str,
            'confidence': float,
            'recommended_action': str
        }
        """
        analysis = {
            'recalibrate': False,
            'reason': None,
            'confidence': 0.0,
            'recommended_action': 'maintain'
        }
        
        # CHECK 1: SUFFICIENT DATA FOR DECISION
        if len(recent_data) < self.min_learning_samples:
            analysis['reason'] = 'insufficient_data'
            analysis['recommended_action'] = 'continue_learning'
            return analysis
        
        if self.baseline_stats is None:
            analysis['recalibrate'] = True
            analysis['reason'] = 'no_baseline_exists'
            analysis['confidence'] = 1.0
            analysis['recommended_action'] = 'full_recalibration'
            return analysis
        
        # CHECK 2: STATISTICAL DRIFT DETECTION
        drift_result = self._detect_statistical_drift(recent_data)
        if drift_result['detected']:
            analysis['recalibrate'] = True
            analysis['reason'] = f"statistical_drift_{drift_result['type']}"
            analysis['confidence'] = drift_result['confidence']
            analysis['recommended_action'] = 'gradual_recalibration'
        
        # CHECK 3: SEASONAL PATTERN CHANGES
        seasonal_result = self._analyze_seasonal_changes(recent_data)
        if seasonal_result['pattern_changed']:
            analysis['recalibrate'] = True
            analysis['reason'] = 'seasonal_pattern_change'
            analysis['confidence'] = max(analysis['confidence'], seasonal_result['confidence'])
            analysis['recommended_action'] = 'seasonal_adjustment'
        
        # CHECK 4: MODEL PERFORMANCE DEGRADATION
        performance = self._evaluate_model_performance(recent_data)
        if performance['mape'] > 15.0:  # 15% MAPE threshold
            analysis['recalibrate'] = True
            if not analysis['reason']:
                analysis['reason'] = 'model_performance_degradation'
            analysis['confidence'] = max(analysis['confidence'], 
                                       min(1.0, performance['mape'] / 50))
            analysis['recommended_action'] = 'model_retraining'
        
        return analysis
    
    def _detect_statistical_drift(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Detect distribution changes using multiple statistical tests"""
        if self.baseline_stats is None:
            return {'detected': False, 'type': None, 'confidence': 0.0}
        
        # Get reference baseline values
        reference_mean = self.baseline_stats.get('mean', 0)
        reference_std = self.baseline_stats.get('std', 1)
        reference_values = np.random.normal(reference_mean, reference_std, 1000)  # Simulate baseline
        
        recent = data['value'].values if 'value' in data.columns else data.values.flatten()
        
        results = {
            'detected': False,
            'type': None,
            'confidence': 0.0
        }
        
        tests = []
        
        # Kolmogorov-Smirnov test for distribution changes
        try:
            ks_stat, ks_p = stats.ks_2samp(reference_values, recent)
            tests.append(('ks_test', ks_p < 0.01, ks_p))
        except Exception as e:
            logger.warning(f"KS test failed: {e}")
        
        # Mann-Whitney U test for median shifts
        try:
            u_stat, u_p = stats.mannwhitneyu(reference_values, recent, alternative='two-sided')
            tests.append(('mannwhitney', u_p < 0.01, u_p))
        except Exception as e:
            logger.warning(f"Mann-Whitney test failed: {e}")
        
        # Variance test (Levene's test)
        try:
            levene_stat, levene_p = stats.levene(reference_values, recent)
            tests.append(('variance_change', levene_p < 0.01, levene_p))
        except Exception as e:
            logger.warning(f"Levene test failed: {e}")
        
        # Calculate confidence score
        significant_tests = [t for t in tests if t[1]]
        if significant_tests:
            results['detected'] = True
            results['type'] = ', '.join([t[0] for t in significant_tests if t[1]])
            
            # Confidence based on p-values and number of agreeing tests
            if tests:
                avg_p_value = np.mean([t[2] for t in significant_tests])
                results['confidence'] = min(1.0, (1 - avg_p_value) * len(significant_tests) / len(tests))
        
        return results
    
    def _analyze_seasonal_changes(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze seasonal pattern changes"""
        # Simplified seasonal analysis
        if len(data) < 24:  # Need at least 24 hours of data
            return {'pattern_changed': False, 'confidence': 0.0}
        
        # Group by hour of day
        if 'timestamp' in data.columns:
            data['hour'] = pd.to_datetime(data['timestamp']).dt.hour
            hourly_means = data.groupby('hour')['value'].mean()
            
            # Compare with baseline seasonal factors if available
            if self.baseline_stats and 'seasonal_factors' in self.baseline_stats:
                baseline_hourly = self.baseline_stats['seasonal_factors'].get('hourly', [])
                if len(baseline_hourly) == 24:
                    # Calculate correlation
                    correlation = np.corrcoef(hourly_means.values, baseline_hourly)[0, 1]
                    
                    if correlation < 0.7:  # Low correlation indicates pattern change
                        return {
                            'pattern_changed': True,
                            'confidence': 1.0 - correlation
                        }
        
        return {'pattern_changed': False, 'confidence': 0.0}
    
    def _evaluate_model_performance(self, data: pd.DataFrame) -> Dict[str, float]:
        """Evaluate baseline model performance"""
        if self.baseline_stats is None:
            return {'mape': 100.0}
        
        baseline_mean = self.baseline_stats.get('mean', 0)
        actual_values = data['value'].values if 'value' in data.columns else data.values.flatten()
        
        # Calculate MAPE (Mean Absolute Percentage Error)
        mape = np.mean(np.abs((actual_values - baseline_mean) / (baseline_mean + 1e-10))) * 100
        
        return {'mape': mape}
    
    def _check_external_factors(self) -> Dict[str, Any]:
        """Check for external factors requiring recalibration"""
        # This would check for network upgrades, device changes, etc.
        # For now, return no external factors
        return {'requires_recalibration': False}
    
    def execute_recalibration(self, data: pd.DataFrame, method: str = 'adaptive') -> Dict[str, Any]:
        """Execute the recalibration with chosen method"""
        recalibration_log = {
            'timestamp': datetime.utcnow().isoformat(),
            'device_ip': self.device_ip,
            'metric': self.metric_type,
            'method': method,
            'samples_used': len(data),
            'previous_baseline': self.baseline_stats.copy() if self.baseline_stats else None,
            'triggers': []
        }
        
        start_time = datetime.utcnow()
        
        if method == 'gradual':
            new_baseline = self._gradual_update(data, alpha=0.1)
        elif method == 'seasonal':
            new_baseline = self._seasonal_adjustment(data)
        elif method == 'full':
            new_baseline = self._full_recalibration(data)
        elif method == 'adaptive':
            # Choose method based on data characteristics
            volatility = data['value'].std() / (data['value'].mean() + 1e-10)
            
            if volatility > 0.5:
                method_used = 'gradual'
                new_baseline = self._gradual_update(data, alpha=0.05)
            else:
                method_used = 'full'
                new_baseline = self._full_recalibration(data)
            
            recalibration_log['method'] = f"adaptive->{method_used}"
        
        # Update baseline
        self.baseline_stats = new_baseline
        self._save_baseline(new_baseline)
        
        # Validate new baseline
        validation = self._validate_baseline(data.tail(20) if len(data) >= 20 else data)
        
        recalibration_log.update({
            'new_baseline': new_baseline,
            'validation_result': validation,
            'execution_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
        })
        
        # Log to database
        self._log_recalibration(recalibration_log)
        
        return recalibration_log
    
    def _gradual_update(self, data: pd.DataFrame, alpha: float) -> Dict[str, Any]:
        """Gradual baseline update using exponential smoothing"""
        if self.baseline_stats is None:
            return self._full_recalibration(data)
        
        current = self.baseline_stats.copy()
        
        # Calculate new values with momentum
        data_mean = data['value'].mean() if 'value' in data.columns else data.values.mean()
        data_std = data['value'].std() if 'value' in data.columns else data.values.std()
        
        current['mean'] = (1 - alpha) * current.get('mean', data_mean) + alpha * data_mean
        current['std'] = (1 - alpha) * current.get('std', data_std) + alpha * data_std
        
        # Calculate percentiles
        if 'value' in data.columns:
            current['p95'] = data['value'].quantile(0.95)
            current['p99'] = data['value'].quantile(0.99)
        
        current['updated_at'] = datetime.utcnow().isoformat()
        
        return current
    
    def _seasonal_adjustment(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Adjust for seasonal patterns"""
        baseline = self._full_recalibration(data)
        
        # Extract seasonal factors
        if 'timestamp' in data.columns:
            data['hour'] = pd.to_datetime(data['timestamp']).dt.hour
            hourly_means = data.groupby('hour')['value'].mean()
            overall_mean = data['value'].mean()
            
            baseline['seasonal_factors'] = {
                'hourly': (hourly_means / overall_mean).tolist()
            }
        
        return baseline
    
    def _full_recalibration(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Complete baseline recalibration"""
        values = data['value'].values if 'value' in data.columns else data.values.flatten()
        
        baseline = {
            'mean': float(np.mean(values)),
            'std': float(np.std(values)),
            'min': float(np.min(values)),
            'max': float(np.max(values)),
            'p25': float(np.percentile(values, 25)),
            'p50': float(np.percentile(values, 50)),
            'p75': float(np.percentile(values, 75)),
            'p95': float(np.percentile(values, 95)),
            'p99': float(np.percentile(values, 99)),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'sample_count': len(values)
        }
        
        return baseline
    
    def _validate_baseline(self, validation_data: pd.DataFrame) -> Dict[str, Any]:
        """Validate new baseline against recent data"""
        if self.baseline_stats is None:
            return {'valid': False, 'reason': 'no_baseline'}
        
        values = validation_data['value'].values if 'value' in validation_data.columns else validation_data.values.flatten()
        baseline_mean = self.baseline_stats.get('mean', 0)
        baseline_std = self.baseline_stats.get('std', 1)
        
        # Check if values are within reasonable range
        within_3sigma = np.sum(np.abs(values - baseline_mean) < 3 * baseline_std) / len(values)
        
        return {
            'valid': within_3sigma > 0.95,  # 95% within 3 sigma
            'within_3sigma_percent': within_3sigma * 100,
            'mean_error': float(np.mean(np.abs(values - baseline_mean)))
        }
    
    def _save_baseline(self, baseline: Dict[str, Any]):
        """Save baseline to database"""
        try:
            db = get_db()
            with db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO device_baselines (device_ip, metric_type, baseline_data, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (device_ip, metric_type)
                    DO UPDATE SET
                        baseline_data = EXCLUDED.baseline_data,
                        updated_at = EXCLUDED.updated_at
                """, (
                    self.device_ip,
                    self.metric_type,
                    json.dumps(baseline)
                ))
            logger.info(f"Saved baseline for {self.device_ip}/{self.metric_type}")
        except Exception as e:
            logger.error(f"Error saving baseline: {e}")
    
    def _log_recalibration(self, log_data: Dict[str, Any]):
        """Log recalibration event"""
        try:
            db = get_db()
            with db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO baseline_recalibration_logs (
                        device_ip, metric_type, recalibration_data, created_at
                    ) VALUES (%s, %s, %s, NOW())
                """, (
                    self.device_ip,
                    self.metric_type,
                    json.dumps(log_data)
                ))
        except Exception as e:
            logger.error(f"Error logging recalibration: {e}")
    
    def get_current_baseline(self) -> Dict[str, Any]:
        """Get current baseline statistics"""
        return self.baseline_stats or {}
    
    def _get_current_baseline_summary(self) -> Dict[str, Any]:
        """Get summary of current baseline"""
        if self.baseline_stats is None:
            return {}
        
        return {
            'mean': self.baseline_stats.get('mean'),
            'std': self.baseline_stats.get('std'),
            'updated_at': self.baseline_stats.get('updated_at')
        }


