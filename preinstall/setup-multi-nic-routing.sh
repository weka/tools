#!/usr/bin/env bash
#
# setup-multi-nic-routing.sh
#
# Configures source-based routing for multiple NICs using NetworkManager.
# Routes are persistent via NM. Handles local subnets and client/default routes.
#
# Supports:
#   --nics             Space-separated list of NICs (required)
#   --client-subnet    Optional remote subnet (CIDR) to route via gateway (can be 0.0.0.0/0)
#   --gateway          Optional gateway for the client subnet
#   --reset            Remove any existing routing rules created by this script
#   --no-mtu           Skip setting MTU=9000 on Ethernet NICs
#   --dry-run          Show intended actions without applying them

set -euo pipefail

ROUTE_TABLE_PREFIX="weka"
SYSCTL_FILE="/etc/sysctl.d/99-weka.conf"
RT_TABLES="/etc/iproute2/rt_tables"
DRY_RUN=false
RESET_MODE=false
NO_MTU=false

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
    local nic="$1"
    local subnet
    subnet=$(ip -o -f inet route show dev "$nic" scope link | awk '{print $1}' | head -n1)
    if [[ -z "$subnet" ]]; then
        echo "⚠️ Could not determine network CIDR for $nic, defaulting to /24"
        ip_only=$(get_ip_for_nic "$nic")
        subnet="${ip_only%/*}/24"
    fi
    echo "$subnet"
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
    if ! $DRY_RUN; then : > "$SYSCTL_FILE"; fi
    for nic in "${NIC_LIST[@]}"; do
        run_or_echo "echo \"net.ipv4.conf.${nic}.arp_filter = 1\" >> \"$SYSCTL_FILE\""
        run_or_echo "echo \"net.ipv4.conf.${nic}.arp_ignore = 1\" >> \"$SYSCTL_FILE\""
        run_or_echo "echo \"net.ipv4.conf.${nic}.arp_announce = 2\" >> \"$SYSCTL_FILE\""
    done
    if ! $DRY_RUN; then sysctl --system >/dev/null; else echo "[dry-run] sysctl --system"; fi
}

find_existing_table_id() {
    local nic="$1"
    grep -E "weka-${nic}" "$RT_TABLES" | awk '{print $1}' | head -n1
}

find_next_table_id() {
    local id=100
    while grep -q "^$id " "$RT_TABLES"; do ((id++)); done
    echo "$id"
}

reset_routing_rules() {
    for nic in "${NIC_LIST[@]}"; do
        echo "🔄 Reset mode — clearing routing rules and persistent NM routes for $nic..."

        # Remove ip rules for this NIC
        ip rule show | grep "weka-${nic}" | while read -r line; do
            prio=$(echo "$line" | awk -F: '{print $1}')
            [[ -n "$prio" ]] && run_or_echo "ip rule del pref $prio"
        done

        # Remove persistent NM routes
        if nmcli -t -f NAME connection show | grep -q "^$nic$"; then
            echo "🧹 Clearing persistent routes for $nic"
            run_or_echo "nmcli connection modify $nic ipv4.routes '' ipv4.routing-rules ''"
            run_or_echo "nmcli connection up $nic"
        fi

        echo "✅ Reset complete for $nic"
    done
    exit 0
}

configure_nic() {
    local nic="$1"
    local ip_spec="$2"
    local gateway="$3"
    local client_subnet="$4"
    local table_name="$5"
    local table_id="$6"

    local ip_only="${ip_spec%%/*}"
    local local_subnet
    local_subnet=$(get_network_cidr "$nic")
    local nic_type
    nic_type=$(nmcli -g GENERAL.TYPE device show "$nic" 2>/dev/null | head -n1)

    echo "⚙️ Configuring $nic (Type: $nic_type, IP: $ip_only, Local subnet: $local_subnet, Table: $table_name)..."

    # Add source-based routing rule
    run_or_echo "nmcli connection modify $nic ipv4.routing-rules \"priority $table_id from $ip_only table $table_id\""

    # Local subnet route (direct route, no gateway)
    run_or_echo "nmcli connection modify $nic +ipv4.routes \"$local_subnet src=$ip_only table=$table_id\""

    # Client subnet / default route (via gateway)
    if [[ -n "$client_subnet" && -n "$gateway" ]]; then
        echo "🌍 Adding client subnet route via gateway $gateway"
        run_or_echo "nmcli connection modify $nic +ipv4.routes \"$client_subnet $gateway table=$table_id\""
    fi

    # Route metric
    run_or_echo "nmcli connection modify $nic ipv4.route-metric 0"

    # Bring connection up
    run_or_echo "nmcli connection up $nic"

    # Set MTU if Ethernet and not disabled
    if [[ "$nic_type" == "ethernet" && $NO_MTU == false ]]; then
        echo "📦 Setting MTU 9000 on $nic"
        run_or_echo "ip link set dev $nic mtu 9000"
    elif [[ "$nic_type" == "ethernet" && $NO_MTU == true ]]; then
        echo "🚫 Skipping MTU change due to --no-mtu flag"
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
    echo "⚙️ Configuring NetworkManager to ignore carrier"
    echo "[main]" > /etc/NetworkManager/conf.d/99-weka-carrier.conf && echo "ignore-carrier=*" >> /etc/NetworkManager/conf.d/99-weka-carrier.conf
fi

echo "✅ Successfully processed ${#NIC_LIST[@]} NIC(s)."

