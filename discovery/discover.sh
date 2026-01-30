#!/bin/bash
# Network Discovery Engine
# Performs network scanning with CIDR support, parallel processing, and comprehensive device detection
#
# Usage: discover.sh --subnet <CIDR> [--interval <seconds>] [--output <file>]
# Example: discover.sh --subnet 192.168.1.0/24 --interval 300

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="${BASE_DIR}/data"
SCAN_DIR="${DATA_DIR}/scans"
LOG_DIR="${DATA_DIR}/logs"
CACHE_DIR="${DATA_DIR}/cache"

# Defaults
SUBNET=""
INTERVAL=0
OUTPUT_FILE=""
PARALLEL_HOSTS=50
PING_TIMEOUT=2
NMAP_TIMEOUT=30
RATE_LIMIT=100
ENABLE_OS_DETECTION=true
ENABLE_PORT_SCAN=true
PORT_SCAN_PORTS="22,80,443,8080,8443"
CACHE_TTL=600

# Signal handling
cleanup() {
    local exit_code=$?
    echo "Cleaning up..." >&2
    # Kill background processes
    jobs -p | xargs -r kill 2>/dev/null || true
    wait
    exit $exit_code
}

trap cleanup EXIT INT TERM

# Logging function
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "{\"timestamp\":\"$timestamp\",\"level\":\"$level\",\"message\":\"$message\"}" | tee -a "${LOG_DIR}/discovery.log"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --subnet)
                SUBNET="$2"
                shift 2
                ;;
            --interval)
                INTERVAL="$2"
                shift 2
                ;;
            --output)
                OUTPUT_FILE="$2"
                shift 2
                ;;
            --parallel)
                PARALLEL_HOSTS="$2"
                shift 2
                ;;
            --timeout)
                PING_TIMEOUT="$2"
                shift 2
                ;;
            *)
                echo "Unknown option: $1" >&2
                exit 1
                ;;
        esac
    done

    if [[ -z "$SUBNET" ]]; then
        echo "Error: --subnet is required" >&2
        exit 1
    fi

    # Validate CIDR notation
    if ! echo "$SUBNET" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$'; then
        echo "Error: Invalid CIDR notation: $SUBNET" >&2
        exit 1
    fi
}

# Calculate subnet range
calculate_subnet_range() {
    local cidr=$1
    local ip=$(echo "$cidr" | cut -d'/' -f1)
    local mask=$(echo "$cidr" | cut -d'/' -f2)
    
    # Convert IP to integer
    IFS='.' read -r i1 i2 i3 i4 <<< "$ip"
    local ip_int=$((i1 * 256**3 + i2 * 256**2 + i3 * 256 + i4))
    
    # Calculate network and broadcast
    local host_bits=$((32 - mask))
    local network=$((ip_int & (0xFFFFFFFF << host_bits)))
    local broadcast=$((network | (0xFFFFFFFF >> mask)))
    
    # Convert back to IP
    local n1=$((network >> 24 & 0xFF))
    local n2=$((network >> 16 & 0xFF))
    local n3=$((network >> 8 & 0xFF))
    local n4=$((network & 0xFF))
    
    local b1=$((broadcast >> 24 & 0xFF))
    local b2=$((broadcast >> 16 & 0xFF))
    local b3=$((broadcast >> 8 & 0xFF))
    local b4=$((broadcast & 0xFF))
    
    echo "${n1}.${n2}.${n3}.${n4}"
    echo "${b1}.${b2}.${b3}.${b4}"
}

# Generate list of IPs to scan
generate_ip_list() {
    local cidr=$1
    local range=$(calculate_subnet_range "$cidr")
    local network=$(echo "$range" | head -1)
    local broadcast=$(echo "$range" | tail -1)
    
    # Use nmap to generate IP list (more reliable)
    nmap -sL -n "$cidr" 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | grep -v "^${network}$" | grep -v "^${broadcast}$"
}

# Ping host with timeout and measure RTT
ping_host() {
    local ip=$1
    local start_time=$(date +%s.%N)
    
    # Use ping with timeout and count
    if ping -c 1 -W "$PING_TIMEOUT" "$ip" >/dev/null 2>&1; then
        local end_time=$(date +%s.%N)
        local rtt=$(echo "$end_time - $start_time" | bc -l 2>/dev/null || echo "0")
        local rtt_ms=$(echo "$rtt * 1000" | bc -l 2>/dev/null || echo "0")
        echo "$rtt_ms"
        return 0
    else
        echo "0"
        return 1
    fi
}

# Get MAC address via ARP
get_mac_address() {
    local ip=$1
    # Check ARP cache
    local mac=$(arp -n "$ip" 2>/dev/null | awk '/^'$ip'/ {print $3}' | tr '[:lower:]' '[:upper:]')
    
    if [[ -z "$mac" ]]; then
        # Try arp-scan if available
        if command -v arp-scan &>/dev/null; then
            mac=$(arp-scan -l -q 2>/dev/null | grep "$ip" | awk '{print $2}' | head -1)
        fi
    fi
    
    echo "$mac"
}

# Lookup vendor from MAC OUI
lookup_vendor() {
    local mac=$1
    if [[ -z "$mac" ]]; then
        echo ""
        return
    fi
    
    # Extract OUI (first 3 octets)
    local oui=$(echo "$mac" | cut -d':' -f1-3 | tr '[:lower:]' '[:upper:]' | tr ':' '-')
    
    # Check local OUI database if available
    if [[ -f "${BASE_DIR}/data/oui.txt" ]]; then
        grep -i "^${oui}" "${BASE_DIR}/data/oui.txt" | cut -f2 | head -1 || echo ""
    else
        # Fallback: try online lookup (can be slow)
        curl -s "https://api.macvendors.com/${mac}" 2>/dev/null || echo ""
    fi
}

# Get hostname
get_hostname() {
    local ip=$1
    # Try reverse DNS
    local hostname=$(getent hosts "$ip" 2>/dev/null | awk '{print $2}' | head -1)
    
    if [[ -z "$hostname" ]]; then
        # Try nslookup
        hostname=$(nslookup "$ip" 2>/dev/null | grep -i "name:" | awk '{print $2}' | head -1)
    fi
    
    echo "${hostname:-}"
}

# Port scan with nmap
scan_ports() {
    local ip=$1
    if [[ "$ENABLE_PORT_SCAN" != "true" ]]; then
        echo "[]"
        return
    fi
    
    # Use nmap with specified ports and timeout
    local ports=$(nmap -Pn -p "$PORT_SCAN_PORTS" --max-rtt-timeout "${NMAP_TIMEOUT}ms" --host-timeout "${NMAP_TIMEOUT}s" "$ip" 2>/dev/null | \
        grep -E '^[0-9]+/(tcp|udp)' | grep open | cut -d'/' -f1 | tr '\n' ',' | sed 's/,$//')
    
    if [[ -n "$ports" ]]; then
        echo "[$ports]"
    else
        echo "[]"
    fi
}

# OS detection with nmap
detect_os() {
    local ip=$1
    if [[ "$ENABLE_OS_DETECTION" != "true" ]]; then
        echo ""
        return
    fi
    
    # Use nmap OS detection (requires root)
    local os=$(nmap -O --max-os-tries 1 "$ip" 2>/dev/null | \
        grep -i "OS details:" | sed 's/OS details: //' | head -1)
    
    echo "$os"
}

# Scan single host
scan_host() {
    local ip=$1
    local scan_id=$2
    
    # Check cache first
    local cache_file="${CACHE_DIR}/host_${ip}.json"
    if [[ -f "$cache_file" ]]; then
        local cache_age=$(($(date +%s) - $(stat -c %Y "$cache_file" 2>/dev/null || echo 0)))
        if [[ $cache_age -lt $CACHE_TTL ]]; then
            cat "$cache_file"
            return 0
        fi
    fi
    
    local result="{"
    result+="\"ip\":\"$ip\","
    
    # Ping test
    local rtt=$(ping_host "$ip")
    if [[ -z "$rtt" ]] || [[ "$rtt" == "0" ]]; then
        result+="\"status\":\"offline\","
        result+="\"response_time_ms\":0,"
        result+="\"last_seen\":\"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\""
        result+="}"
        echo "$result"
        return 1
    fi
    
    result+="\"status\":\"online\","
    result+="\"response_time_ms\":$rtt,"
    
    # Get MAC address
    local mac=$(get_mac_address "$ip")
    if [[ -n "$mac" ]]; then
        result+="\"mac\":\"$mac\","
        
        # Lookup vendor
        local vendor=$(lookup_vendor "$mac")
        if [[ -n "$vendor" ]]; then
            result+="\"vendor\":\"$vendor\","
        fi
    fi
    
    # Get hostname
    local hostname=$(get_hostname "$ip")
    if [[ -n "$hostname" ]]; then
        result+="\"hostname\":\"$hostname\","
    fi
    
    # OS detection
    local os=$(detect_os "$ip")
    if [[ -n "$os" ]]; then
        result+="\"os_family\":\"$os\","
    fi
    
    # Port scan
    local ports=$(scan_ports "$ip")
    result+="\"open_ports\":$ports,"
    
    result+="\"last_seen\":\"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\""
    result+="}"
    
    # Cache result
    mkdir -p "$CACHE_DIR"
    echo "$result" > "$cache_file"
    
    echo "$result"
}

# Main scan function
perform_scan() {
    local cidr=$1
    local scan_id=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local start_time=$(date +%s.%N)
    
    log "INFO" "Starting scan of $cidr (scan_id: $scan_id)"
    
    # Generate IP list
    local ip_list=$(generate_ip_list "$cidr")
    local total_hosts=$(echo "$ip_list" | wc -l)
    
    log "INFO" "Scanning $total_hosts hosts in parallel (max $PARALLEL_HOSTS)"
    
    # Create output structure
    local output="{"
    output+="\"scan_id\":\"$scan_id\","
    output+="\"subnet\":\"$cidr\","
    output+="\"devices\":["
    
    # Process hosts in parallel with rate limiting
    local device_count=0
    local online_count=0
    local offline_count=0
    local devices_json=""
    
    # Use xargs for parallel processing
    while IFS= read -r ip; do
        [[ -z "$ip" ]] && continue
        
        # Rate limiting: wait if too many processes
        while [[ $(jobs -r | wc -l) -ge $PARALLEL_HOSTS ]]; do
            sleep 0.1
        done
        
        # Scan in background
        (
            local host_result=$(scan_host "$ip" "$scan_id" 2>/dev/null || echo "")
            if [[ -n "$host_result" ]]; then
                echo "$host_result"
            fi
        ) &
        
    done <<< "$ip_list"
    
    # Wait for all background jobs
    wait
    
    # Collect results (from cache files)
    local first=true
    while IFS= read -r ip; do
        [[ -z "$ip" ]] && continue
        
        local cache_file="${CACHE_DIR}/host_${ip}.json"
        if [[ -f "$cache_file" ]]; then
            local host_data=$(cat "$cache_file")
            if echo "$host_data" | grep -q '"status":"online"'; then
                ((online_count++))
            else
                ((offline_count++))
            fi
            
            if [[ "$first" == "true" ]]; then
                first=false
            else
                devices_json+=","
            fi
            devices_json+="$host_data"
            ((device_count++))
        fi
    done <<< "$ip_list"
    
    output+="$devices_json"
    output+="],"
    
    # Calculate scan duration
    local end_time=$(date +%s.%N)
    local duration=$(echo "$end_time - $start_time" | bc -l 2>/dev/null || echo "0")
    
    # Calculate packet loss (rough estimate)
    local packet_loss=0
    if [[ $total_hosts -gt 0 ]]; then
        packet_loss=$(echo "scale=2; ($offline_count * 100) / $total_hosts" | bc -l 2>/dev/null || echo "0")
    fi
    
    output+="\"metadata\":{"
    output+="\"scan_duration_seconds\":$duration,"
    output+="\"devices_found\":$device_count,"
    output+="\"devices_online\":$online_count,"
    output+="\"devices_offline\":$offline_count,"
    output+="\"packet_loss_percent\":$packet_loss"
    output+="}"
    output+="}"
    
    # Output result
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "$output" | jq '.' > "$OUTPUT_FILE"
        log "INFO" "Scan results written to $OUTPUT_FILE"
    else
        local output_file="${SCAN_DIR}/scan_${scan_id}.json"
        mkdir -p "$SCAN_DIR"
        echo "$output" | jq '.' > "$output_file"
        log "INFO" "Scan results written to $output_file"
    fi
    
    echo "$output" | jq '.'
    
    log "INFO" "Scan completed: $device_count devices found ($online_count online, $offline_count offline) in ${duration}s"
}

# Main execution
main() {
    # Create necessary directories
    mkdir -p "$SCAN_DIR" "$LOG_DIR" "$CACHE_DIR"
    
    # Parse arguments
    parse_args "$@"
    
    # Check dependencies
    if ! command -v nmap &>/dev/null; then
        log "ERROR" "nmap is required but not installed"
        exit 1
    fi
    
    if ! command -v jq &>/dev/null; then
        log "ERROR" "jq is required but not installed"
        exit 1
    fi
    
    # Perform scan
    if [[ $INTERVAL -gt 0 ]]; then
        # Continuous scanning mode
        log "INFO" "Starting continuous scanning (interval: ${INTERVAL}s)"
        while true; do
            perform_scan "$SUBNET"
            sleep "$INTERVAL"
        done
    else
        # Single scan
        perform_scan "$SUBNET"
    fi
}

# Run main function
main "$@"


