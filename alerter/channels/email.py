"""Email alert channel"""
import logging
import os
from ..engine import AlertChannel, Alert

logger = logging.getLogger(__name__)

class EmailChannel(AlertChannel):
    """Email alert channel"""
    
    async def send(self, alert: Alert) -> bool:
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            email_config = self.config.get('alerting', {}).get('channels', {}).get('email', {})
            
            msg = MIMEMultipart()
            msg['From'] = email_config.get('from_address', 'netmon@example.com')
            msg['To'] = ', '.join(email_config.get('to_addresses', []))
            msg['Subject'] = f"[{alert.severity.upper()}] Network Alert: {alert.alert_type}"
            
            body = alert.message
            msg.attach(MIMEText(body, 'plain'))
            
            smtp = aiosmtplib.SMTP(
                hostname=email_config.get('smtp_host', 'localhost'),
                port=email_config.get('smtp_port', 587),
                use_tls=True
            )
            
            await smtp.connect()
            await smtp.login(
                email_config.get('smtp_user', ''),
                email_config.get('smtp_password', '')
            )
            await smtp.send_message(msg)
            await smtp.quit()
            
            return True
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False


