#!/bin/bash
# Development startup script
# Starts all services for local development

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Network Monitor Development Environment${NC}"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/.deps_installed" ]; then
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    pip install --upgrade pip
    pip install fastapi uvicorn pydantic psycopg2-binary sqlalchemy pyyaml aiosmtplib python-telegram-bot watchdog
    touch venv/.deps_installed
fi

# Check database connection
echo -e "${YELLOW}Checking database connection...${NC}"
if ! python3 -c "from database.db_connection import get_db; db = get_db(); exit(0 if db.health_check() else 1)" 2>/dev/null; then
    echo -e "${RED}Database connection failed!${NC}"
    echo "Please ensure PostgreSQL is running and configured in config.yaml"
    exit 1
fi

# Create necessary directories
mkdir -p data/scans data/logs data/cache

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping services...${NC}"
    kill $API_PID $PROCESSOR_PID $ALERTER_PID 2>/dev/null || true
    wait
    echo -e "${GREEN}Services stopped${NC}"
    exit 0
}

trap cleanup INT TERM

# Start API
echo -e "${GREEN}Starting API server...${NC}"
cd api
python main.py &
API_PID=$!
cd ..

# Wait for API to start
sleep 3

# Start Processor
echo -e "${GREEN}Starting Processor...${NC}"
cd processor
python main.py &
PROCESSOR_PID=$!
cd ..

# Start Alerter
echo -e "${GREEN}Starting Alerter...${NC}"
cd alerter
python main.py &
ALERTER_PID=$!
cd ..

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}Services Started Successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  API Server:     http://localhost:8080"
echo "  API Docs:       http://localhost:8080/docs"
echo "  Health Check:   http://localhost:8080/health"
echo ""
echo "  Processor PID:  $PROCESSOR_PID"
echo "  Alerter PID:    $ALERTER_PID"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for all background processes
wait


