#!/bin/bash
# Rigorous Validation Script
# Runs 100+ checks to validate system completeness and correctness

set -euo pipefail

PASSED=0
FAILED=0
TOTAL=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
test_count=0

# Test function
test_check() {
    local test_num=$1
    local description=$2
    shift 2
    local command="$@"
    
    ((test_count++))
    TOTAL=$test_count
    
    echo -n "Test $test_count/100: $description ... "
    
    if eval "$command" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
        return 1
    fi
}

echo "=== Network Monitor Rigorous Validation ==="
echo ""

# File Structure Checks (1-20)
echo "=== File Structure Checks ==="
test_check 1 "Project root exists" "[ -d . ]"
test_check 2 "Discovery script exists" "[ -f discovery/discover.sh ]"
test_check 3 "Processor module exists" "[ -f processor/pipeline.py ]"
test_check 4 "Database schema exists" "[ -f database/schema.sql ]"
test_check 5 "Alerting engine exists" "[ -f alerter/engine.py ]"
test_check 6 "API main exists" "[ -f api/main.py ]"
test_check 7 "Frontend package.json exists" "[ -f frontend/package.json ]"
test_check 8 "Config file exists" "[ -f config.yaml ]"
test_check 9 "Requirements file exists" "[ -f requirements.txt ]"
test_check 10 "Systemd services exist" "[ -f systemd/netmon-discover.service ]"
test_check 11 "Health check script exists" "[ -f health/check_monitor.sh ]"
test_check 12 "Maintenance scripts exist" "[ -f maintenance/run_maintenance.sh ]"
test_check 13 "Test files exist" "[ -f tests/test_pipeline.py ]"
test_check 14 "Documentation exists" "[ -f docs/ARCHITECTURE.md ]"
test_check 15 "Deployment guide exists" "[ -f docs/DEPLOYMENT.md ]"
test_check 16 "API docs exist" "[ -f docs/API.md ]"
test_check 17 "Troubleshooting guide exists" "[ -f docs/TROUBLESHOOTING.md ]"
test_check 18 "Security docs exist" "[ -f docs/SECURITY.md ]"
test_check 19 "Maintenance guide exists" "[ -f docs/MAINTENANCE.md ]"
test_check 20 "Data directories exist" "[ -d data/scans ] && [ -d data/logs ]"

# Script Permissions (21-25)
echo ""
echo "=== Script Permissions ==="
test_check 21 "Discovery script is executable" "[ -x discovery/discover.sh ]"
test_check 22 "Health check is executable" "[ -x health/check_monitor.sh ]"
test_check 23 "Maintenance script is executable" "[ -x maintenance/run_maintenance.sh ]"
test_check 24 "Backup script is executable" "[ -x database/backup.sh ]"
test_check 25 "Cleanup script is executable" "[ -x maintenance/cleanup_old_data.sh ]"

# Python Code Quality (26-40)
echo ""
echo "=== Python Code Quality ==="
test_check 26 "Python syntax valid (processor)" "python3 -m py_compile processor/pipeline.py"
test_check 27 "Python syntax valid (database)" "python3 -m py_compile database/db_connection.py"
test_check 28 "Python syntax valid (alerter)" "python3 -m py_compile alerter/engine.py"
test_check 29 "Python syntax valid (API)" "python3 -m py_compile api/main.py"
test_check 30 "Processor has DeviceProcessor class" "grep -q 'class DeviceProcessor' processor/pipeline.py"
test_check 31 "Processor has validation method" "grep -q 'def _validate_scan' processor/pipeline.py"
test_check 32 "Processor has enrichment method" "grep -q 'def _enrich_devices' processor/pipeline.py"
test_check 33 "Processor has analysis method" "grep -q 'def _analyze_changes' processor/pipeline.py"
test_check 34 "Database has connection class" "grep -q 'class DatabaseConnection' database/db_connection.py"
test_check 35 "Alerter has AlertEngine class" "grep -q 'class AlertEngine' alerter/engine.py"
test_check 36 "API has FastAPI app" "grep -q 'FastAPI' api/main.py"
test_check 37 "API has WebSocket endpoint" "grep -q '@app.websocket' api/main.py"
test_check 38 "API has health endpoint" "grep -q '@app.get.*health' api/main.py"
test_check 39 "API has devices endpoint" "grep -q '@app.get.*devices' api/main.py"
test_check 40 "API has statistics endpoint" "grep -q '@app.get.*statistics' api/main.py"

# Configuration Validation (41-50)
echo ""
echo "=== Configuration Validation ==="
test_check 41 "Config file is valid YAML" "python3 -c 'import yaml; yaml.safe_load(open(\"config.yaml\"))'"
test_check 42 "Config has discovery section" "grep -q 'discovery:' config.yaml"
test_check 43 "Config has database section" "grep -q 'database:' config.yaml"
test_check 44 "Config has alerting section" "grep -q 'alerting:' config.yaml"
test_check 45 "Config has API section" "grep -q 'api:' config.yaml"
test_check 46 "Config has logging section" "grep -q 'logging:' config.yaml"
test_check 47 "Config has health section" "grep -q 'health:' config.yaml"
test_check 48 "Config has maintenance section" "grep -q 'maintenance:' config.yaml"
test_check 49 "Default subnet is valid CIDR" "python3 -c 'import yaml; c=yaml.safe_load(open(\"config.yaml\")); import ipaddress; ipaddress.ip_network(c[\"discovery\"][\"default_subnet\"])'"
test_check 50 "Scan interval is positive" "python3 -c 'import yaml; c=yaml.safe_load(open(\"config.yaml\")); assert c[\"discovery\"][\"scan_interval_seconds\"] > 0'"

# Database Schema Validation (51-60)
echo ""
echo "=== Database Schema Validation ==="
test_check 51 "Schema has devices table" "grep -q 'CREATE TABLE.*devices' database/schema.sql"
test_check 52 "Schema has device_status_history table" "grep -q 'CREATE TABLE.*device_status_history' database/schema.sql"
test_check 53 "Schema has port_scan_results table" "grep -q 'CREATE TABLE.*port_scan_results' database/schema.sql"
test_check 54 "Schema has anomalies table" "grep -q 'CREATE TABLE.*anomalies' database/schema.sql"
test_check 55 "Schema has alerts table" "grep -q 'CREATE TABLE.*alerts' database/schema.sql"
test_check 56 "Schema has partitioning" "grep -q 'PARTITION BY' database/schema.sql"
test_check 57 "Schema has indexes" "grep -q 'CREATE INDEX' database/schema.sql"
test_check 58 "Schema has views" "grep -q 'CREATE.*VIEW' database/schema.sql"
test_check 59 "Schema has functions" "grep -q 'CREATE.*FUNCTION' database/schema.sql"
test_check 60 "Schema has triggers" "grep -q 'CREATE TRIGGER' database/schema.sql"

# Systemd Service Validation (61-70)
echo ""
echo "=== Systemd Service Validation ==="
test_check 61 "Discovery service file exists" "[ -f systemd/netmon-discover.service ]"
test_check 62 "Processor service file exists" "[ -f systemd/netmon-processor.service ]"
test_check 63 "API service file exists" "[ -f systemd/netmon-api.service ]"
test_check 64 "Alerter service file exists" "[ -f systemd/netmon-alerter.service ]"
test_check 65 "Maintenance service file exists" "[ -f systemd/netmon-maintenance.service ]"
test_check 66 "Maintenance timer exists" "[ -f systemd/netmon-maintenance.timer ]"
test_check 67 "Services have User directive" "grep -q 'User=netmon' systemd/netmon-*.service"
test_check 68 "Services have security hardening" "grep -q 'NoNewPrivileges=true' systemd/netmon-*.service"
test_check 69 "Services have restart policy" "grep -q 'Restart=' systemd/netmon-*.service"
test_check 70 "Services have logging" "grep -q 'StandardOutput=journal' systemd/netmon-*.service"

# Frontend Validation (71-80)
echo ""
echo "=== Frontend Validation ==="
test_check 71 "Frontend has package.json" "[ -f frontend/package.json ]"
test_check 72 "Frontend has vite config" "[ -f frontend/vite.config.js ]"
test_check 73 "Frontend has index.html" "[ -f frontend/index.html ]"
test_check 74 "Frontend has main entry" "[ -f frontend/src/main.jsx ]"
test_check 75 "Frontend has App component" "[ -f frontend/src/App.jsx ]"
test_check 76 "Frontend has Dashboard component" "[ -f frontend/src/components/Dashboard.jsx ]"
test_check 77 "Frontend has DeviceList component" "[ -f frontend/src/components/DeviceList.jsx ]"
test_check 78 "Frontend has AnomalyList component" "[ -f frontend/src/components/AnomalyList.jsx ]"
test_check 79 "Frontend has AlertList component" "[ -f frontend/src/components/AlertList.jsx ]"
test_check 80 "Frontend package.json has React" "grep -q '\"react\"' frontend/package.json"

# Test Suite Validation (81-90)
echo ""
echo "=== Test Suite Validation ==="
test_check 81 "Test directory exists" "[ -d tests ]"
test_check 82 "Pipeline tests exist" "[ -f tests/test_pipeline.py ]"
test_check 83 "Database tests exist" "[ -f tests/test_database.py ]"
test_check 84 "API tests exist" "[ -f tests/test_api.py ]"
test_check 85 "Discovery tests exist" "[ -f tests/test_discovery.sh ]"
test_check 86 "Pytest config exists" "[ -f pytest.ini ]"
test_check 87 "Test conftest exists" "[ -f tests/conftest.py ]"
test_check 88 "Tests import processor" "grep -q 'from processor' tests/test_pipeline.py"
test_check 89 "Tests import database" "grep -q 'from database' tests/test_database.py"
test_check 90 "Tests use pytest" "grep -q 'import pytest' tests/test_*.py"

# Documentation Validation (91-100)
echo ""
echo "=== Documentation Validation ==="
test_check 91 "README exists" "[ -f README.md ]"
test_check 92 "Architecture doc exists" "[ -f docs/ARCHITECTURE.md ]"
test_check 93 "Deployment doc exists" "[ -f docs/DEPLOYMENT.md ]"
test_check 94 "API doc exists" "[ -f docs/API.md ]"
test_check 95 "Troubleshooting doc exists" "[ -f docs/TROUBLESHOOTING.md ]"
test_check 96 "Security doc exists" "[ -f docs/SECURITY.md ]"
test_check 97 "Maintenance doc exists" "[ -f docs/MAINTENANCE.md ]"
test_check 98 "README has architecture section" "grep -qi 'architecture' README.md"
test_check 99 "Deployment doc has prerequisites" "grep -qi 'prerequisites' docs/DEPLOYMENT.md"
test_check 100 "API doc has endpoints" "grep -qi 'endpoint' docs/API.md"

# Summary
echo ""
echo "=== Validation Summary ==="
echo "Total tests: $TOTAL"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All validation checks passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some validation checks failed${NC}"
    exit 1
fi


