#!/bin/bash
# Health Monitoring Script
# Monitors the monitoring system itself

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${BASE_DIR}/data/logs"
ALERT_SCRIPT="${BASE_DIR}/alerter/send_alert.sh"

# Configuration
DISK_THRESHOLD=85
SCAN_TIMEOUT=600  # 10 minutes

# Logging
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}" | tee -a "${LOG_DIR}/health.log"
}

# Check if service is running
check_service() {
    local service=$1
    if systemctl is-active --quiet "$service"; then
        log "INFO" "Service $service is running"
        return 0
    else
        log "ERROR" "Service $service is not running"
        systemctl restart "$service"
        log "INFO" "Attempted to restart service $service"
        return 1
    fi
}

# Check disk space
check_disk_space() {
    local usage=$(df "${BASE_DIR}/data" --output=pcent | tail -1 | tr -d '% ' | tr -d '%')
    if [ "$usage" -gt "$DISK_THRESHOLD" ]; then
        log "WARNING" "Disk usage at ${usage}% (threshold: ${DISK_THRESHOLD}%)"
        # Trigger cleanup
        if [ -f "${BASE_DIR}/maintenance/cleanup_old_data.sh" ]; then
            "${BASE_DIR}/maintenance/cleanup_old_data.sh" --days 30
        fi
        return 1
    else
        log "INFO" "Disk usage: ${usage}%"
        return 0
    fi
}

# Check database connectivity
check_database() {
    if command -v pg_isready &>/dev/null; then
        if pg_isready -h localhost -U netmon -d netmon >/dev/null 2>&1; then
            log "INFO" "Database is responding"
            return 0
        else
            log "ERROR" "Database is not responding"
            return 1
        fi
    else
        # Fallback: try to connect via Python
        if python3 -c "from database.db_connection import get_db; db = get_db(); exit(0 if db.health_check() else 1)" 2>/dev/null; then
            log "INFO" "Database is responding"
            return 0
        else
            log "ERROR" "Database is not responding"
            return 1
        fi
    fi
}

# Check scan completion
check_scan_completion() {
    local scan_dir="${BASE_DIR}/data/scans"
    if [ ! -d "$scan_dir" ]; then
        log "WARNING" "Scan directory does not exist: $scan_dir"
        return 1
    fi
    
    # Find most recent scan file
    local last_scan=$(find "$scan_dir" -name "*.json" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)
    
    if [ -z "$last_scan" ]; then
        log "WARNING" "No scan files found"
        return 1
    fi
    
    local now=$(date +%s)
    local diff=$((now - ${last_scan%.*}))
    
    if [ "$diff" -gt "$SCAN_TIMEOUT" ]; then
        log "ERROR" "No scans in ${diff} seconds (threshold: ${SCAN_TIMEOUT}s)"
        return 1
    else
        log "INFO" "Last scan was ${diff} seconds ago"
        return 0
    fi
}

# Diagnose scan failure
diagnose_scan_failure() {
    log "INFO" "Diagnosing scan failure..."
    
    # Check if discovery service is running
    if ! systemctl is-active --quiet netmon-discover; then
        log "ERROR" "Discovery service is not running"
        return
    fi
    
    # Check network connectivity
    if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        log "ERROR" "No internet connectivity"
        return
    fi
    
    # Check if nmap is available
    if ! command -v nmap &>/dev/null; then
        log "ERROR" "nmap is not installed"
        return
    fi
    
    # Check permissions
    if [ ! -w "${BASE_DIR}/data/scans" ]; then
        log "ERROR" "No write permission to scan directory"
        return
    fi
    
    log "INFO" "Scan failure diagnosis complete"
}

# Main health check
main() {
    log "INFO" "Starting health check"
    
    local errors=0
    
    # Check services
    check_service "netmon-discover" || ((errors++))
    check_service "netmon-processor" || ((errors++))
    check_service "netmon-api" || ((errors++))
    check_service "netmon-alerter" || ((errors++))
    
    # Check disk space
    check_disk_space || ((errors++))
    
    # Check database
    check_database || ((errors++))
    
    # Check scan completion
    check_scan_completion || {
        ((errors++))
        diagnose_scan_failure
    }
    
    if [ $errors -eq 0 ]; then
        log "INFO" "All health checks passed"
        exit 0
    else
        log "ERROR" "Health check failed with $errors errors"
        exit 1
    fi
}

main "$@"


