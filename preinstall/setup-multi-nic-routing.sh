#!/usr/bin/env bash
#
# setup-multi-nic-routing.sh
#
# This script configures source-based routing for multiple NICs using NetworkManager.
#
# For each specified NIC:
#   - Validates the interface is present and up
#   - Retrieves its IPv4 address and subnet
#   - Creates a dedicated routing table (e.g. weka-eth0, weka-eth1, ...)
#   - Adds a source-based routing rule for traffic from that IP
#   - Adds a route to the local subnet via the same interface and IP
#   - Optionally adds a route to a remote client subnet via a specified gateway
#   - Enables ARP tuning (arp_filter=1, arp_announce=2) only for the listed NICs
#   - Sets MTU=9000 for Ethernet interfaces (unless --no-mtu is used)
#
# Supports:
#   --nics             Space-separated list of NICs (required)
#   --client-subnet    Optional remote subnet (CIDR format) to route via gateway (could be 0.0.0.0/0)
#   --gateway          Optional gateway for the client subnet
#   --reset            Removes any existing source-based routing rules created by this script
#   --no-mtu           Skip setting MTU=9000 for Ethernet NICs
#   --dry-run          Show intended actions without applying them
#
# Example usage:
#   ./setup-multi-nic-routing.sh --nics eth0 eth1 --client-subnet 192.168.50.0/24 --gateway 10.0.0.254
#   ./setup-multi-nic-routing.sh --nics eth0 eth1 --client-subnet 0.0.0.0/0 --gateway 10.1.1.254
#   ./setup-multi-nic-routing.sh --nics ib0 ib1                      # Flat IB or Ethernet (no gateway)
#   ./setup-multi-nic-routing.sh --nics eth0 eth1 --reset            # Remove only routing rules
#   ./setup-multi-nic-routing.sh --nics eth0 eth1 --no-mtu           # Skip MTU 9000 change
#   ./setup-multi-nic-routing.sh --nics eth0 eth1 --dry-run          # Preview only
#

set -euo pipefail

# ---- CONFIG ----
ROUTE_TABLE_PREFIX="weka"
SYSCTL_FILE="/etc/sysctl.d/99-weka.conf"
RT_TABLES="/etc/iproute2/rt_tables"
DRY_RUN=false
RESET_MODE=false
NO_MTU=false

# ---- FUNCTIONS ----

usage() {
    echo "Usage: $0 --nics <nic1> [nic2 ...] [--client-subnet <CIDR>] [--gateway <IP>] [--reset] [--no-mtu] [--dry-run]"
    exit 1
}

errmsg() {
    echo "[ERROR] $*" >&2
}

run_or_echo() {
    if $DRY_RUN; then
        echo "[dry-run] $*"
    else
        eval "$@"
    fi
}

check_requirements() {
    for cmd in nmcli ip ipcalc; do
        command -v $cmd >/dev/null || { errmsg "$cmd not found"; exit 1; }
    done
}

validate_nic() {
    local nic="$1"
    ip link show "$nic" &>/dev/null || { errmsg "NIC $nic not found"; exit 1; }
    ip link show up "$nic" | grep -q "$nic" || { errmsg "NIC $nic is down"; exit 1; }
}

get_ip_for_nic() {
    ip -4 addr show "$1" | awk '/inet / {print $2}' | head -n1
}

get_network_cidr() {
    local ip_cidr="$1"
    ipcalc "$ip_cidr" 2>/dev/null | awk '/^Network:/ {print $2}'
}

ensure_rt_table() {
    local table_id="$1"
    local table_name="$2"
    if ! grep -qw "$table_name" "$RT_TABLES"; then
        run_or_echo "echo \"$table_id $table_name\" >> \"$RT_TABLES\""
    fi
}

apply_sysctl_arp_settings() {
    echo "🔧 Setting ARP tuning in $SYSCTL_FILE for interfaces: ${NIC_LIST[*]}"
    if ! $DRY_RUN; then
        : > "$SYSCTL_FILE"
    fi
    for nic in "${NIC_LIST[@]}"; do
        run_or_echo "echo \"net.ipv4.conf.${nic}.arp_filter = 1\" >> \"$SYSCTL_FILE\""
        run_or_echo "echo \"net.ipv4.conf.${nic}.arp_ignore = 1\" >> \"$SYSCTL_FILE\""
        run_or_echo "echo \"net.ipv4.conf.${nic}.arp_announce = 2\" >> \"$SYSCTL_FILE\""
    done
    if ! $DRY_RUN; then
        sysctl --system >/dev/null
    else
        echo "[dry-run] sysctl --system"
    fi
}

find_existing_table_id() {
    local nic="$1"
    grep -E "weka-${nic}" "$RT_TABLES" | awk '{print $1}' | head -n1
}

find_next_table_id() {
    awk '$1 ~ /^[0-9]+$/ {print $1}' "$RT_TABLES" | sort -n | tail -1 | awk '{print $1+1}'
}

reset_routing_rules() {
    for nic in "${NIC_LIST[@]}"; do
        echo "🧹 Resetting rules for $nic..."
        local ip_spec
        ip_spec=$(get_ip_for_nic "$nic")
        local ip_only="${ip_spec%%/*}"
        ip rule show | grep -w "$ip_only" | awk -F: '{print $1}' | while read -r rule_id; do
            run_or_echo "ip rule del pref $rule_id"
        done
    done
    echo "✅ Reset complete — existing routing rules removed (interfaces untouched)."
    exit 0
}

configure_nic() {
    local nic="$1"
    local ip_spec="$2"
    local gateway="$3"
    local client_subnet="$4"
    local table_name="$5"
    local table_id="$6"

    local local_subnet
    local_subnet=$(get_network_cidr "$ip_spec")
    local ip_only="${ip_spec%%/*}"
    local nic_type
    nic_type=$(nmcli -g GENERAL.TYPE device show "$nic" 2>/dev/null | head -n1)

    echo "⚙️  Configuring $nic (Type: $nic_type, IP: $ip_only, Local subnet: $local_subnet, Table: $table_name)..."

    # Configure routing rule
    if ! ip rule show | grep -q "from $ip_only lookup $table_name"; then
        run_or_echo "ip rule add from $ip_only table $table_name pref $table_id"
    else
        echo "ℹ️  Rule already exists for $ip_only → table $table_name"
    fi

    # Local subnet route
    run_or_echo "ip route replace $local_subnet dev $nic src $ip_only table $table_name"

    # Optional client subnet route (skip main if 0.0.0.0/0)
    if [[ -n "$client_subnet" && -n "$gateway" ]]; then
        if [[ "$client_subnet" == "0.0.0.0/0" ]]; then
            echo "🌍 Adding default route (client subnet) to table $table_name only"
            run_or_echo "ip route replace default via $gateway dev $nic table $table_name"
        else
            echo "📡 Adding route to client subnet: $client_subnet via $gateway"
            run_or_echo "ip route replace $client_subnet via $gateway dev $nic table $table_name"
        fi
    fi

    # Set MTU if Ethernet and not disabled
    if [[ "$nic_type" == "ethernet" && $NO_MTU == false ]]; then
        echo "📦 Setting MTU 9000 on $nic (Ethernet)"
        run_or_echo "ip link set dev $nic mtu 9000"
    elif [[ "$nic_type" == "ethernet" && $NO_MTU == true ]]; then
        echo "🚫 Skipping MTU change on $nic (Ethernet) due to --no-mtu flag"
    fi
}

# ---- MAIN ----

NIC_LIST=()
CLIENT_SUBNET=""
GATEWAY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --nics)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                NIC_LIST+=("$1")
                shift
            done
            ;;
        --client-subnet)
            CLIENT_SUBNET="$2"
            shift 2
            ;;
        --gateway)
            GATEWAY="$2"
            shift 2
            ;;
        --reset)
            RESET_MODE=true
            shift
            ;;
        --no-mtu)
            NO_MTU=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            errmsg "Unknown argument: $1"
            usage
            ;;
    esac
done

if [[ ${#NIC_LIST[@]} -lt 1 ]]; then
    errmsg "At least one NIC must be specified"
    usage
fi

check_requirements
apply_sysctl_arp_settings

if $RESET_MODE; then
    reset_routing_rules
fi

for nic in "${NIC_LIST[@]}"; do
    validate_nic "$nic"
    ip_spec=$(get_ip_for_nic "$nic")
    if [[ -z "$ip_spec" ]]; then
        errmsg "No IP address found on NIC $nic"
        exit 1
    fi

    table_id=$(find_existing_table_id "$nic" || true)
    if [[ -z "$table_id" ]]; then
        table_id=$(find_next_table_id)
        table_name="${ROUTE_TABLE_PREFIX}-${nic}"
        ensure_rt_table "$table_id" "$table_name"
    else
        table_name=$(grep -E "^[[:space:]]*$table_id" "$RT_TABLES" | awk '{print $2}')
    fi

    configure_nic "$nic" "$ip_spec" "$GATEWAY" "$CLIENT_SUBNET" "$table_name" "$table_id"
done

if ! $DRY_RUN; then
    echo "⚙️  Configuring NetworkManager to ignore carrier"
    echo "[main]" > /etc/NetworkManager/conf.d/99-weka-carrier.conf && echo "ignore-carrier=*" >> /etc/NetworkManager/conf.d/99-weka-carrier.conf
fi

echo "✅ Successfully processed ${#NIC_LIST[@]} NIC(s)."

