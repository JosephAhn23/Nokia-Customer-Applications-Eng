#!/bin/bash
# Database Backup Script
# Creates automated backups with retention policy

set -euo pipefail

# Configuration
BACKUP_DIR="/opt/netmon/data/backups"
RETENTION_DAYS=30
DB_NAME="${NETMON_DB_NAME:-netmon}"
DB_USER="${NETMON_DB_USER:-netmon}"
DB_HOST="${NETMON_DB_HOST:-localhost}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/netmon_backup_${TIMESTAMP}.sql.gz"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Perform backup
echo "Starting database backup..."
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    --no-owner --no-acl \
    | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup completed: $BACKUP_FILE"
    
    # Get backup size
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup size: $SIZE"
    
    # Cleanup old backups
    echo "Cleaning up backups older than $RETENTION_DAYS days..."
    find "$BACKUP_DIR" -name "netmon_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
    
    echo "Backup process completed successfully"
    exit 0
else
    echo "ERROR: Backup failed!"
    exit 1
fi


