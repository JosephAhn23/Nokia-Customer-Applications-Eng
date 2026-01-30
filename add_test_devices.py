#!/usr/bin/env python3
"""Quick script to add test devices to the database for demo purposes"""

import os
import sys
from datetime import datetime
import uuid

# Set password before importing database module
os.environ['NETMON_DB_PASSWORD'] = 'netmon123'

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_connection import get_db

def add_test_devices():
    """Add sample devices for demo"""
    db = get_db()
    
    test_devices = [
        {
            "ip": "192.168.1.1",
            "mac": "00:11:22:33:44:55",
            "vendor": "Cisco Systems",
            "hostname": "router.local",
            "device_type": "router",
            "status": "online",
            "response_time_ms": 12.5
        },
        {
            "ip": "192.168.1.10",
            "mac": "AA:BB:CC:DD:EE:01",
            "vendor": "Dell Inc",
            "hostname": "server-01.local",
            "device_type": "server",
            "status": "online",
            "response_time_ms": 8.3
        },
        {
            "ip": "192.168.1.25",
            "mac": "FF:EE:DD:CC:BB:AA",
            "vendor": "HP Inc",
            "hostname": "printer-01.local",
            "device_type": "printer",
            "status": "online",
            "response_time_ms": 45.2
        },
        {
            "ip": "192.168.1.50",
            "mac": "11:22:33:44:55:66",
            "vendor": "Unknown",
            "hostname": None,
            "device_type": "iot_device",
            "status": "degraded",
            "response_time_ms": 250.0
        },
        {
            "ip": "192.168.1.100",
            "mac": "22:33:44:55:66:77",
            "vendor": "Apple Inc",
            "hostname": "laptop-mac.local",
            "device_type": "unknown",
            "status": "offline",
            "response_time_ms": None
        }
    ]
    
    with db.get_cursor() as cursor:
        scan_id = uuid.uuid4()
        
        for device in test_devices:
            # Insert or update device
            cursor.execute("""
                INSERT INTO devices (ip_address, mac_address, vendor, hostname, device_type, risk_score, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ip_address, mac_address) 
                DO UPDATE SET
                    vendor = EXCLUDED.vendor,
                    hostname = EXCLUDED.hostname,
                    device_type = EXCLUDED.device_type,
                    last_seen = EXCLUDED.last_seen
                RETURNING device_id
            """, (
                device['ip'],
                device['mac'],
                device['vendor'],
                device['hostname'],
                device['device_type'],
                0  # risk_score
            ))
            
            device_result = cursor.fetchone()
            device_id = device_result['device_id']
            
            # Insert status history
            cursor.execute("""
                INSERT INTO device_status_history (device_id, status, response_time_ms, timestamp, scan_id)
                VALUES (%s, %s, %s, NOW(), %s)
            """, (
                device_id,
                device['status'],
                device['response_time_ms'],
                str(scan_id)
            ))
        
        # Commit is handled by the context manager
        print(f"[OK] Added {len(test_devices)} test devices to database")
        print("Refresh your API endpoint to see them!")

if __name__ == "__main__":
    try:
        add_test_devices()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

