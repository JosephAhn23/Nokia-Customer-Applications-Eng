#!/bin/bash
# Network Monitor Installation Script
# Run as root or with sudo

set -euo pipefail

INSTALL_DIR="/opt/netmon"
SERVICE_USER="netmon"

echo "=== Network Monitor Installation ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root or with sudo"
    exit 1
fi

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Creating service user: $SERVICE_USER"
    useradd -r -s /bin/bash -d "$INSTALL_DIR" "$SERVICE_USER"
fi

# Create directory structure
echo "Creating directory structure..."
mkdir -p "$INSTALL_DIR"/{discovery,processor,database,alerter,api,frontend,health,maintenance,tests,data/{scans,logs},docs}

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    nmap arp-scan iputils-ping \
    jq curl \
    nodejs npm \
    bats

# Create Python virtual environment
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# Set permissions
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR"/discovery/*.sh
chmod +x "$INSTALL_DIR"/health/*.sh
chmod +x "$INSTALL_DIR"/maintenance/*.sh

echo "Installation complete!"
echo "Next steps:"
echo "1. Configure PostgreSQL database (see DEPLOYMENT.md)"
echo "2. Copy systemd service files to /etc/systemd/system/"
echo "3. Configure alerting channels in config.yaml"
echo "4. Start services: systemctl start netmon-*"


