#!/bin/bash
# Maintenance Script Runner
# Executes all maintenance tasks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log "Starting maintenance tasks"

# Run database cleanup
if [ -f "${SCRIPT_DIR}/cleanup_old_data.sh" ]; then
    log "Running data cleanup..."
    "${SCRIPT_DIR}/cleanup_old_data.sh" --days 90
fi

# Run database backup
if [ -f "${BASE_DIR}/database/backup.sh" ]; then
    log "Running database backup..."
    "${BASE_DIR}/database/backup.sh"
fi

# Run database vacuum
log "Running database vacuum..."
python3 -c "
from database.db_connection import get_db
db = get_db()
with db.get_connection() as conn:
    conn.cursor().execute('VACUUM ANALYZE')
"

# Run index maintenance
if [ -f "${SCRIPT_DIR}/index_maintenance.sh" ]; then
    log "Running index maintenance..."
    "${SCRIPT_DIR}/index_maintenance.sh"
fi

log "Maintenance tasks completed"

