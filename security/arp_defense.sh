#!/bin/bash
# MULTI-LAYER ARP SPOOFING DEFENSE
# Production-grade ARP cache poisoning countermeasures

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${BASE_DIR}/data/logs"
DB_PATH="${BASE_DIR}/data/devices.db"

# Configuration
INTERFACE="${ARP_DEFENSE_INTERFACE:-eth0}"
CHECK_INTERVAL=300  # 5 minutes
ALERT_THRESHOLD=5   # Number of flips before alert

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}" | tee -a "${LOG_DIR}/arp_defense.log"
}

# LAYER 1: PASSIVE DETECTION
detect_arp_anomalies() {
    log "INFO" "Starting ARP anomaly detection cycle"
    
    # Capture ARP traffic (requires root or capabilities)
    if command -v tcpdump &>/dev/null && [ "$EUID" -eq 0 ]; then
        timeout 60 tcpdump -n -i "$INTERFACE" -e arp -w /tmp/arp_capture_$$.pcap -c 1000 2>/dev/null &
        TCPDUMP_PID=$!
        sleep 5
        kill $TCPDUMP_PID 2>/dev/null || true
        wait $TCPDUMP_PID 2>/dev/null || true
        
        if [ -f "/tmp/arp_capture_$$.pcap" ]; then
            analyze_arp_pcap "/tmp/arp_capture_$$.pcap"
            rm -f "/tmp/arp_capture_$$.pcap"
        fi
    else
        log "WARNING" "tcpdump not available or not running as root, skipping packet capture"
    fi
}

analyze_arp_pcap() {
    local pcap_file=$1
    
    # Use Python for analysis if scapy is available
    python3 << EOF 2>/dev/null || log "WARNING" "ARP analysis requires Python scapy library"
import sys
import json
from collections import defaultdict
from datetime import datetime

try:
    from scapy.all import rdpcap, ARP
except ImportError:
    print(json.dumps({"error": "scapy not installed"}))
    sys.exit(1)

class ARPDefender:
    def __init__(self):
        self.known_bindings = {}
        self.suspicious_events = []
        self.flip_counts = defaultdict(int)
        
    def analyze_pcap(self, pcap_file):
        try:
            packets = rdpcap(pcap_file)
        except Exception as e:
            return {"error": str(e)}
        
        for pkt in packets:
            if ARP in pkt:
                self._process_arp_packet(pkt)
        
        return self._generate_report()
    
    def _process_arp_packet(self, pkt):
        sender_ip = pkt[ARP].psrc
        sender_mac = pkt[ARP].hwsrc
        opcode = pkt[ARP].op
        
        # RULE 1: MULTIPLE MACs FOR SINGLE IP
        if sender_ip in self.known_bindings:
            known_mac = self.known_bindings[sender_ip]
            
            if known_mac.lower() != sender_mac.lower():
                # Extract OUI (first 3 octets)
                vendor_oui = sender_mac[:8].replace(':', '').upper()
                known_oui = known_mac[:8].replace(':', '').upper()
                
                if vendor_oui != known_oui:
                    self.suspicious_events.append({
                        'timestamp': datetime.utcnow().isoformat(),
                        'type': 'mac_flip_different_manufacturer',
                        'ip': sender_ip,
                        'old_mac': known_mac,
                        'new_mac': sender_mac,
                        'confidence': 'HIGH',
                        'recommended_action': 'BLOCK_AND_ALERT'
                    })
                
                self.flip_counts[sender_ip] += 1
                
                if self.flip_counts[sender_ip] > ${ALERT_THRESHOLD}:
                    self.suspicious_events.append({
                        'timestamp': datetime.utcnow().isoformat(),
                        'type': 'rapid_mac_flipping',
                        'ip': sender_ip,
                        'flip_count': self.flip_counts[sender_ip],
                        'confidence': 'CRITICAL',
                        'recommended_action': 'ISOLATE_PORT'
                    })
        
        self.known_bindings[sender_ip] = sender_mac
        
    def _generate_report(self):
        return {
            'total_bindings': len(self.known_bindings),
            'suspicious_events': self.suspicious_events,
            'flip_counts': dict(self.flip_counts)
        }

defender = ARPDefender()
result = defender.analyze_pcap('${pcap_file}')
print(json.dumps(result, indent=2))
EOF
}

# LAYER 2: ACTIVE DEFENSE - ARP CACHE VALIDATION
validate_arp_cache() {
    log "INFO" "Starting ARP cache validation"
    
    # Get current ARP cache
    arp -n 2>/dev/null | awk '/^[0-9]/ {print $1 " " $3}' > /tmp/current_arp.txt || return 1
    
    local anomalies=0
    
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        
        ip=$(echo "$line" | awk '{print $1}')
        mac=$(echo "$line" | awk '{print $2}')
        
        # Check 1: MAC format validation
        if ! [[ "$mac" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
            log "WARNING" "INVALID_MAC_FORMAT: $ip -> $mac"
            log_anomaly "invalid_mac" "$ip" "$mac"
            ((anomalies++))
            continue
        fi
        
        # Check 2: Active validation via ping and ARP
        if ping -c 1 -W 2 "$ip" >/dev/null 2>&1; then
            # Verify ARP entry is still correct
            current_arp_mac=$(arp -n "$ip" 2>/dev/null | awk '/^'$ip'/ {print $3}')
            
            if [ -n "$current_arp_mac" ] && [ "$current_arp_mac" != "$mac" ]; then
                log "ERROR" "ARP_CACHE_MISMATCH: $ip changed from $mac to $current_arp_mac"
                log_anomaly "arp_mismatch" "$ip" "$mac" "$current_arp_mac"
                ((anomalies++))
            fi
        fi
        
    done < /tmp/current_arp.txt
    
    rm -f /tmp/current_arp.txt
    
    if [ $anomalies -gt 0 ]; then
        log "WARNING" "Detected $anomalies ARP anomalies"
        return 1
    else
        log "INFO" "ARP cache validation passed"
        return 0
    fi
}

log_anomaly() {
    local type=$1
    shift
    local details="$*"
    
    # Store in database or log file
    echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ")|$type|$details" >> "${LOG_DIR}/arp_anomalies.log"
    
    # Send alert if critical
    if [ "$type" = "rapid_mac_flipping" ] || [ "$type" = "mac_flip_different_manufacturer" ]; then
        send_alert "arp_spoofing" "$type: $details"
    fi
}

send_alert() {
    local alert_type=$1
    local message=$2
    
    # Send via configured alerting system
    python3 << EOF 2>/dev/null || true
from alerter.engine import AlertEngine
import asyncio

alerter = AlertEngine()
anomaly = {
    'type': '${alert_type}',
    'device': 'network',
    'severity': 'high',
    'description': '${message}',
    'timestamp': '$(date -u +"%Y-%m-%dT%H:%M:%SZ")'
}
asyncio.run(alerter.process_anomalies([anomaly]))
EOF
}

quarantine_device() {
    local ip=$1
    local mac=$2
    
    log "WARNING" "QUARANTINING $ip ($mac)"
    
    # Block at firewall (requires root)
    if [ "$EUID" -eq 0 ]; then
        iptables -C FORWARD -s "$ip" -j DROP 2>/dev/null || iptables -A FORWARD -s "$ip" -j DROP
        iptables -C FORWARD -d "$ip" -j DROP 2>/dev/null || iptables -A FORWARD -d "$ip" -j DROP
        log "INFO" "Firewall rules added for $ip"
    else
        log "WARNING" "Cannot add firewall rules (not running as root)"
    fi
    
    # Send alert
    send_alert "arp_quarantine" "Device $ip ($mac) quarantined due to ARP spoofing"
}

# Main monitoring loop
main() {
    log "INFO" "Starting ARP Defense System"
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    while true; do
        detect_arp_anomalies
        validate_arp_cache
        
        sleep "$CHECK_INTERVAL"
    done
}

# Run if executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi


