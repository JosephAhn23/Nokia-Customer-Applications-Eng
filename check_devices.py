import os
os.environ['NETMON_DB_PASSWORD'] = 'netmon123'
import psycopg2

conn = psycopg2.connect(host='localhost', database='netmon', user='netmon', password='netmon123')
cur = conn.cursor()

# Check devices table
print("=== Devices Table ===")
cur.execute("SELECT device_id, ip_address, hostname, device_type FROM devices")
devices = cur.fetchall()
print(f"Found {len(devices)} devices:")
for d in devices:
    print(f"  {d}")

# Check view
print("\n=== device_current_status View ===")
cur.execute("SELECT device_id, ip_address, hostname, status FROM device_current_status")
view_devices = cur.fetchall()
print(f"Found {len(view_devices)} devices in view:")
for d in view_devices:
    print(f"  {d}")

# Check status history
print("\n=== Status History ===")
cur.execute("SELECT COUNT(*) FROM device_status_history")
count = cur.fetchone()[0]
print(f"Status history records: {count}")

conn.close()

