#!/bin/bash
# Cleanup Old Data Script
# Removes old scan files and database records based on retention policy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
SCAN_DIR="${BASE_DIR}/data/scans"
RETENTION_DAYS=90

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --days)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log "Starting data cleanup (retention: ${RETENTION_DAYS} days)"

# Cleanup old scan files
if [ -d "$SCAN_DIR" ]; then
    log "Cleaning up old scan files..."
    find "$SCAN_DIR" -name "*.json" -type f -mtime +$RETENTION_DAYS -delete
    log "Scan file cleanup completed"
fi

# Cleanup old database records
log "Cleaning up old database records..."
python3 << EOF
from database.db_connection import get_db
from datetime import datetime, timedelta

db = get_db()
cutoff_date = datetime.utcnow() - timedelta(days=$RETENTION_DAYS)

with db.get_cursor() as cursor:
    # Delete old status history
    cursor.execute("""
        DELETE FROM device_status_history
        WHERE timestamp < %s
    """, (cutoff_date,))
    deleted = cursor.rowcount
    print(f"Deleted {deleted} old status history records")
    
    # Delete old port scan results
    cursor.execute("""
        DELETE FROM port_scan_results
        WHERE scan_timestamp < %s
    """, (cutoff_date,))
    deleted = cursor.rowcount
    print(f"Deleted {deleted} old port scan results")
    
    # Delete old resolved anomalies
    cursor.execute("""
        DELETE FROM anomalies
        WHERE resolved_at IS NOT NULL
          AND resolved_at < %s
    """, (cutoff_date,))
    deleted = cursor.rowcount
    print(f"Deleted {deleted} old resolved anomalies")
EOF

log "Data cleanup completed"


