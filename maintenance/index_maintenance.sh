#!/bin/bash
# Index Maintenance Script
# Runs database index maintenance procedures

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

DB_NAME="${NETMON_DB_NAME:-netmon}"
DB_USER="${NETMON_DB_USER:-netmon}"
DB_HOST="${NETMON_DB_HOST:-localhost}"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log "Starting index maintenance"

# Run maintenance procedure
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" << EOF
CALL maintain_indexes(
    fragmentation_threshold := 30.0,
    max_reindex_time := '02:00:00'::interval
);
EOF

if [ $? -eq 0 ]; then
    log "Index maintenance completed successfully"
    
    # Refresh materialized view
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "REFRESH MATERIALIZED VIEW index_fragmentation_trends;" || true
    
    exit 0
else
    log "ERROR: Index maintenance failed"
    exit 1
fi


