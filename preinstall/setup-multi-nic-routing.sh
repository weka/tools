setup-multi-nic-routing.sh#!/usr/bin/env bash
#
# setup-multi-nic-routing.sh
# v1.0
#
# Configures source-based routing for multiple NICs using NetworkManager.
#
# Features:
#   - Validates NICs are present and up
#   - Creates dedicated routing tables: weka-<nic>
#   - Adds source-based routing rules
#   - Routes local subnet and optional client subnet via NIC
#   - Enables ARP tuning (arp_filter/arp_announce)
#   - Sets MTU=9000 for Ethernet interfaces
#   - --reset: removes rules/routes only, preserves NM connections
#   - Supports multi-run, multi-NIC, different subnets safely
#
# Usage examples:
#   ./setup-multi-nic-routing.sh --nics ib0 ib1
#   ./setup-multi-nic-routing.sh --nics eth0 eth1 --client-subnet 192.168.50.0/24 --gateway 10.0.0.254
#   ./setup-multi-nic-routing.sh --nics ens19 ens20 --reset
#   ./setup-multi-nic-routing.sh --nics eth0 --client-subnet 0.0.0.0/0 --gateway 10.1.1.254
#   ./setup-multi-nic-routing.sh --nics eth1 --client-subnet 0.0.0.0/0 --gateway 10.1.2.254
#

set -euo pipefail

# ---- CONFIG ----
ROUTE_TABLE_PREFIX="weka"
SYSCTL_FILE="/etc/sysctl.d/99-weka.conf"
RT_TABLES="/etc/iproute2/rt_tables"
DRY_RUN=false
RESET=false

# ---- FUNCTIONS ----

usage() {
    echo "Usage: $0 --nics <nic1> [nic2 ...] [--client-subnet <CIDR>] [--gateway <IP>] [--dry-run] [--reset]"
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
    local network_line
    network_line=$(ipcalc "$ip_cidr" 2>/dev/null | awk '/^Network:/ {print $2}')
    echo "$network_line"
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

# Reset rules only (do NOT delete NM connection)
reset_nic_config() {
    local nic="$1"
    local table_name="${ROUTE_TABLE_PREFIX}-${nic}"

    echo "🧹 Resetting routing rules for $nic ..."

    # Remove matching ip rules
    local rules
    rules=$(ip rule show | grep -w "lookup" | grep "$table_name" || true)
    if [[ -n "$rules" ]]; then
        echo "$rules" | while read -r rule; do
            local priority
            priority=$(echo "$rule" | awk '{print $1}' | sed 's/://')
            run_or_echo "ip rule del priority $priority"
        done
    else
        echo "  No ip rules found for $table_name"
    fi

    # Flush the routing table
    run_or_echo "ip route flush table $table_name || true"

    echo "  ✅ Routing rules cleared for $nic"
}

# Get or allocate a routing table ID (ensure unique)
get_or_allocate_table_id() {
    local nic="$1"
    local table_name="${ROUTE_TABLE_PREFIX}-${nic}"

    # Reuse table if it exists
    local existing_entry
    existing_entry=$(grep -w "$table_name" "$RT_TABLES" | awk '{print $1}' || true)
    if [[ -n "$existing_entry" ]]; then
        echo "$existing_entry"
        return
    fi

    # Allocate next free numeric ID starting from 100
    local used_ids
    used_ids=$(awk '{print $1}' "$RT_TABLES" | grep -E '^[0-9]+$' | sort -n | uniq)
    local id=100
    while echo "$used_ids" | grep -qw "$id"; do
        ((id++))
    done

    run_or_echo "echo \"$id $table_name\" >> \"$RT_TABLES\""
    echo "$id"
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
    local con_name="${nic}"
    local nic_type
    nic_type=$(nmcli -g GENERAL.TYPE device show "$nic" 2>/dev/null | head -n1)

    echo "⚙️  Configuring $nic (Type: $nic_type, IP: $ip_only, Local subnet: $local_subnet, Table: $table_name)..."

    run_or_echo "nmcli con delete \"$con_name\" &>/dev/null || true"

    run_or_echo "nmcli con add type \"$nic_type\" ifname \"$nic\" con-name \"$con_name\" \
        ipv4.addresses \"$ip_spec\" \
        ipv4.method manual \
        connection.autoconnect yes \
        ipv4.route-metric 0 \
        ipv4.routing-rules \"priority $table_id from $ip_only table $table_id\""

    if [[ "$nic_type" == "ethernet" ]]; then
        echo "📦 Setting MTU 9000 on $nic (Ethernet)"
        run_or_echo "nmcli con modify \"$con_name\" 802-3-ethernet.mtu 9000"
    fi

    # Add local subnet route
    echo "🔁 Adding route to local subnet: $local_subnet src=$ip_only table=$table_id"
    run_or_echo "nmcli connection modify \"$con_name\" +ipv4.routes \"$local_subnet src=$ip_only table=$table_id\""

    # Add client subnet route
    if [[ -n "$client_subnet" && -n "$gateway" ]]; then
        echo "📡 Adding route to client subnet: $client_subnet via $gateway (table: $table_name)"
        # Always add to NIC's custom table
        run_or_echo "nmcli connection modify \"$con_name\" +ipv4.routes \"$client_subnet $gateway table=$table_id\""

        # Only add to main table if not default route
        if [[ "$client_subnet" != "0.0.0.0/0" ]]; then
            run_or_echo "nmcli connection modify \"$con_name\" +ipv4.routes \"$client_subnet $gateway\""
        else
            echo "⚠️ Skipping adding 0.0.0.0/0 to main routing table; route exists only in $table_name"
        fi
    fi

    run_or_echo "nmcli con down \"$con_name\""
    run_or_echo "nmcli con up \"$con_name\""
}

# ---- MAIN ----

NIC_LIST=()
CLIENT_SUBNET=""
GATEWAY=""

# Parse CLI arguments
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
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --reset)
            RESET=true
            shift
            ;;
        *)
            errmsg "Unknown argument: $1"
            usage
            ;;
    esac
done

# Validate input
if [[ ${#NIC_LIST[@]} -lt 1 ]]; then
    errmsg "At least one NIC must be specified"
    usage
fi

check_requirements

# ---- RESET MODE ----
if $RESET; then
    echo "🔄 Reset mode enabled — clearing routing rules and tables for specified NICs."
    for nic in "${NIC_LIST[@]}"; do
        reset_nic_config "$nic"
    done
    echo "✅ Reset complete. NM connections and ARP settings preserved."
    exit 0
fi

# ---- NORMAL CONFIGURATION ----
apply_sysctl_arp_settings

for nic in "${NIC_LIST[@]}"; do
    validate_nic "$nic"
    ip_spec=$(get_ip_for_nic "$nic")
    if [[ -z "$ip_spec" ]]; then
        errmsg "No IP address found on NIC $nic"
        exit 1
    fi

    table_name="${ROUTE_TABLE_PREFIX}-${nic}"
    table_id=$(get_or_allocate_table_id "$nic")

    configure_nic "$nic" "$ip_spec" "$GATEWAY" "$CLIENT_SUBNET" "$table_name" "$table_id"
done

if ! $DRY_RUN; then
    echo "⚙️  Configuring NetworkManager to ignore carrier"
    echo "[main]" > /etc/NetworkManager/conf.d/99-weka-carrier.conf
    echo "ignore-carrier=*" >> /etc/NetworkManager/conf.d/99-weka-carrier.conf
fi

echo "✅ ${DRY_RUN:-false}" | grep -q true && tag='[dry-run] ' || tag=''
echo "✅ ${tag}Successfully processed ${#NIC_LIST[@]} NIC(s)."

