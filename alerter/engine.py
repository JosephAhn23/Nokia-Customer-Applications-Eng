"""
Alerting Engine
Multi-channel alerting with escalation policies and deduplication
"""

import asyncio
import logging
import hashlib
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import yaml
from pathlib import Path

from database.db_connection import get_db

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """Alert data structure"""
    alert_id: Optional[int] = None
    anomaly_id: Optional[int] = None
    device_id: Optional[int] = None
    alert_type: str = ""
    severity: str = "medium"
    channel: str = ""
    message: str = ""
    metadata: Dict = None


class AlertEngine:
    """Main alerting engine"""
    
    # Default alert rules
    ALERT_RULES = {
        'sudden_downtime': {
            'channels': ['email', 'telegram'],
            'throttle_minutes': 5,
            'escalation': [
                {'after_minutes': 15, 'add_channel': 'sms'},
                {'after_minutes': 60, 'severity': 'critical'}
            ]
        },
        'new_ports_opened': {
            'channels': ['email', 'dashboard'],
            'require_acknowledgment': True,
            'whitelist_ports': [80, 443, 22]
        },
        'latency_spike': {
            'channels': ['dashboard'],
            'threshold_minutes': 30,
            'aggregate': True
        },
        'new_device': {
            'channels': ['dashboard', 'email'],
            'throttle_minutes': 60
        },
        'ports_closed': {
            'channels': ['dashboard'],
            'severity': 'low'
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.db = get_db()
        self.alert_tracking: Dict[str, Dict] = {}
        self._load_alert_rules()
        self._initialize_channels()
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("Config file not found, using defaults")
            return {}
    
    def _load_alert_rules(self):
        """Load alert rules from config"""
        rules = self.config.get('alerting', {}).get('rules', {})
        if rules:
            self.ALERT_RULES.update(rules)
    
    def _initialize_channels(self):
        """Initialize alert channels"""
        self.channels = {}
        
        # Email channel
        if self.config.get('alerting', {}).get('channels', {}).get('email', {}).get('enabled', False):
            try:
                from .channels.email import EmailChannel
                self.channels['email'] = EmailChannel(self.config)
            except ImportError as e:
                logger.warning(f"Email channel not available: {e}")
        
        # Telegram channel
        if self.config.get('alerting', {}).get('channels', {}).get('telegram', {}).get('enabled', False):
            try:
                from .channels.telegram import TelegramChannel
                self.channels['telegram'] = TelegramChannel(self.config)
            except ImportError as e:
                logger.warning(f"Telegram channel not available: {e}")
        
        # Dashboard channel (always enabled)
        try:
            from .channels.dashboard import DashboardChannel
            self.channels['dashboard'] = DashboardChannel(self.config)
        except ImportError as e:
            logger.warning(f"Dashboard channel not available: {e}")
    
    def _generate_alert_key(self, anomaly: Dict) -> str:
        """Generate unique key for alert deduplication"""
        device = anomaly.get('device', 'unknown')
        anomaly_type = anomaly.get('type', 'unknown')
        return f"{device}:{anomaly_type}"
    
    def _is_duplicate_alert(self, anomaly: Dict) -> bool:
        """Check if this is a duplicate alert"""
        alert_key = self._generate_alert_key(anomaly)
        
        # Check in-memory tracking
        if alert_key in self.alert_tracking:
            tracking = self.alert_tracking[alert_key]
            if not tracking.get('resolved', False):
                return True
        
        # Check database
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT tracking_id, last_occurrence, occurrence_count, throttle_until
                    FROM alert_tracking
                    WHERE alert_key = %s AND resolved = FALSE
                """, (alert_key,))
                result = cursor.fetchone()
                
                if result:
                    # Update occurrence count
                    cursor.execute("""
                        UPDATE alert_tracking
                        SET occurrence_count = occurrence_count + 1,
                            last_occurrence = NOW()
                        WHERE tracking_id = %s
                    """, (result['tracking_id'],))
                    return True
        except Exception as e:
            logger.error(f"Error checking duplicate alert: {e}")
        
        return False
    
    def _should_alert_now(self, anomaly: Dict, rule: Dict) -> bool:
        """Check if alert should be sent now (throttling)"""
        throttle_minutes = rule.get('throttle_minutes', 0)
        if throttle_minutes == 0:
            return True
        
        alert_key = self._generate_alert_key(anomaly)
        
        # Check database for throttle
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT throttle_until, last_alert_sent
                    FROM alert_tracking
                    WHERE alert_key = %s
                """, (alert_key,))
                result = cursor.fetchone()
                
                if result and result.get('throttle_until'):
                    throttle_until = result['throttle_until']
                    if datetime.now() < throttle_until:
                        logger.debug(f"Alert throttled until {throttle_until}")
                        return False
        except Exception as e:
            logger.error(f"Error checking throttle: {e}")
        
        return True
    
    def _create_alert(self, anomaly: Dict, rule: Dict, device_id: Optional[int] = None) -> Alert:
        """Create alert object from anomaly"""
        severity = anomaly.get('severity', rule.get('severity', 'medium'))
        alert_type = anomaly.get('type', 'unknown')
        
        # Build message
        message = self._build_alert_message(anomaly)
        
        alert = Alert(
            anomaly_id=anomaly.get('anomaly_id'),
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            metadata=anomaly
        )
        
        return alert
    
    def _build_alert_message(self, anomaly: Dict) -> str:
        """Build human-readable alert message"""
        anomaly_type = anomaly.get('type', 'unknown')
        device = anomaly.get('device', 'Unknown')
        device_name = anomaly.get('device_name', device)
        severity = anomaly.get('severity', 'medium')
        
        messages = {
            'sudden_downtime': f"⚠️ Device {device_name} ({device}) has gone offline unexpectedly. "
                              f"Previous uptime: {anomaly.get('previous_uptime', 0):.1%}",
            
            'new_ports_opened': f"🔓 New ports opened on {device_name} ({device}): {', '.join(map(str, anomaly.get('ports', [])))}",
            
            'latency_spike': f"⏱️ Latency spike detected on {device_name} ({device}). "
                            f"Current: {anomaly.get('current', 0):.2f}ms, "
                            f"Baseline: {anomaly.get('baseline', 0):.2f}ms "
                            f"(+{anomaly.get('increase_percent', 0):.1f}%)",
            
            'new_device': f"🆕 New device detected: {device_name} ({device}). "
                         f"MAC: {anomaly.get('mac', 'unknown')}, "
                         f"Vendor: {anomaly.get('vendor', 'unknown')}",
            
            'ports_closed': f"🔒 Ports closed on {device_name} ({device}): {', '.join(map(str, anomaly.get('ports', [])))}"
        }
        
        base_message = messages.get(anomaly_type, f"Anomaly detected: {anomaly_type} on {device_name}")
        
        # Add timestamp
        timestamp = anomaly.get('timestamp', datetime.utcnow().isoformat())
        base_message += f"\nDetected at: {timestamp}"
        
        return base_message
    
    def _store_alert_tracking(self, alert: Alert, anomaly: Dict):
        """Store alert tracking information"""
        alert_key = self._generate_alert_key(anomaly)
        rule = self.ALERT_RULES.get(anomaly.get('type', ''), {})
        throttle_minutes = rule.get('throttle_minutes', 0)
        
        throttle_until = None
        if throttle_minutes > 0:
            throttle_until = datetime.utcnow() + timedelta(minutes=throttle_minutes)
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO alert_tracking 
                    (alert_key, first_occurrence, last_occurrence, occurrence_count, last_alert_sent, throttle_until, resolved)
                    VALUES (%s, NOW(), NOW(), 1, NOW(), %s, FALSE)
                    ON CONFLICT (alert_key) 
                    DO UPDATE SET
                        last_occurrence = NOW(),
                        occurrence_count = alert_tracking.occurrence_count + 1,
                        last_alert_sent = NOW(),
                        throttle_until = %s
                """, (alert_key, throttle_until, throttle_until))
        except Exception as e:
            logger.error(f"Error storing alert tracking: {e}")
    
    def _store_alert(self, alert: Alert) -> int:
        """Store alert in database"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO alerts 
                    (anomaly_id, device_id, alert_type, severity, channel, message, sent_at, delivered)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), FALSE)
                    RETURNING alert_id
                """, (
                    alert.anomaly_id,
                    alert.device_id,
                    alert.alert_type,
                    alert.severity,
                    alert.channel,
                    alert.message
                ))
                result = cursor.fetchone()
                return result['alert_id'] if result else None
        except Exception as e:
            logger.error(f"Error storing alert: {e}")
            return None
    
    async def _send_alert(self, channel_name: str, alert: Alert) -> bool:
        """Send alert via specified channel"""
        channel = self.channels.get(channel_name)
        if not channel:
            logger.warning(f"Channel {channel_name} not available")
            return False
        
        try:
            success = await channel.send(alert)
            if success:
                logger.info(f"Alert sent via {channel_name}: {alert.alert_type}")
            return success
        except Exception as e:
            logger.error(f"Error sending alert via {channel_name}: {e}")
            return False
    
    async def process_anomalies(self, anomalies: List[Dict]):
        """Process anomalies and generate alerts"""
        if not self.config.get('alerting', {}).get('enabled', True):
            logger.debug("Alerting is disabled")
            return
        
        for anomaly in anomalies:
            anomaly_type = anomaly.get('type')
            rule = self.ALERT_RULES.get(anomaly_type)
            
            if not rule:
                logger.debug(f"No alert rule for anomaly type: {anomaly_type}")
                continue
            
            # Deduplication check
            if self._is_duplicate_alert(anomaly):
                logger.debug(f"Duplicate alert suppressed: {anomaly_type} on {anomaly.get('device')}")
                continue
            
            # Throttling check
            if not self._should_alert_now(anomaly, rule):
                logger.debug(f"Alert throttled: {anomaly_type} on {anomaly.get('device')}")
                continue
            
            # Get device_id from database
            device_id = None
            device_ip = anomaly.get('device')
            if device_ip:
                try:
                    with self.db.get_cursor() as cursor:
                        cursor.execute("SELECT device_id FROM devices WHERE ip_address = %s", (device_ip,))
                        result = cursor.fetchone()
                        if result:
                            device_id = result['device_id']
                except Exception as e:
                    logger.error(f"Error looking up device: {e}")
            
            # Create alert
            alert = self._create_alert(anomaly, rule, device_id)
            
            # Send via all configured channels
            channels = rule.get('channels', ['dashboard'])
            for channel_name in channels:
                alert.channel = channel_name
                alert_id = self._store_alert(alert)
                if alert_id:
                    alert.alert_id = alert_id
                
                success = await self._send_alert(channel_name, alert)
                
                # Update delivery status
                if alert_id:
                    try:
                        with self.db.get_cursor() as cursor:
                            cursor.execute("""
                                UPDATE alerts 
                                SET delivered = %s, delivery_error = %s
                                WHERE alert_id = %s
                            """, (success, None if success else "Channel error", alert_id))
                    except Exception as e:
                        logger.error(f"Error updating alert delivery status: {e}")
            
            # Store tracking
            self._store_alert_tracking(alert, anomaly)
    
    def acknowledge_alert(self, alert_id: int, acknowledged_by: str) -> bool:
        """Acknowledge an alert"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE alerts
                    SET acknowledged_at = NOW(), acknowledged_by = %s
                    WHERE alert_id = %s
                """, (acknowledged_by, alert_id))
                return True
        except Exception as e:
            logger.error(f"Error acknowledging alert: {e}")
            return False


# Alert channel base class
class AlertChannel:
    """Base class for alert channels"""
    
    def __init__(self, config: Dict):
        self.config = config
    
    async def send(self, alert: Alert) -> bool:
        """Send alert - must be implemented by subclasses"""
        raise NotImplementedError

