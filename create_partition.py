import os
os.environ['NETMON_DB_PASSWORD'] = 'netmon123'
import psycopg2

conn = psycopg2.connect(host='localhost', database='netmon', user='netmon', password='netmon123')
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS device_status_history_y2026m01 PARTITION OF device_status_history FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')")
conn.commit()
print('[OK] Partition created')
conn.close()

