#!/usr/bin/env python3
"""Run database schema"""

import os
os.environ['NETMON_DB_PASSWORD'] = 'netmon123'

import psycopg2
from pathlib import Path

# Read schema file
schema_path = Path(__file__).parent / "database" / "schema.sql"
with open(schema_path, 'r') as f:
    schema_sql = f.read()

# Connect and execute
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="netmon",
    user="netmon",
    password="netmon123"
)

try:
    cursor = conn.cursor()
    cursor.execute(schema_sql)
    conn.commit()
    print("[OK] Schema created successfully!")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()

