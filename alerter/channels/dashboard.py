"""Dashboard alert channel"""
from ..engine import AlertChannel, Alert

class DashboardChannel(AlertChannel):
    """Dashboard channel - stores alerts for web UI"""
    
    async def send(self, alert: Alert) -> bool:
        # Dashboard alerts are stored in database, so always successful
        return True


