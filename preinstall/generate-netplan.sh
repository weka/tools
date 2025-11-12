#!/usr/bin/env bash
#
# generate-netplan.sh
#
# Generate a netplan YAML file for multiple NICs with source-based routing.
# Local subnets are link-scoped (no via), default route uses gateway if provided.
# Also generates sysctl file for ARP tuning and NUMA balancing.
# Does not apply netplan automatically; admin can review before applying.
# Optional flags:
#   --no-mtu         : Do not set MTU to 9000
#   --renderer       : Choose networkd (default) or NetworkManager
#   --apply-sysctl   : Apply sysctl immediately after generating

set -euo pipefail

OUTPUT_FILE="99-weka-netplan.yaml"
SYSCTL_FILE="99-weka-sysctl.conf"
NIC_LIST=()
GATEWAY=""
START_TABLE=101
MTU=9000
NO_MTU=false
APPLY_SYSCTL=false
RENDERER="networkd"

usage() {
    echo "Usage: $0 --nics <nic1> [nic2 ...] [--gateway <IP>] [--no-mtu] [--renderer networkd|NetworkManager] [--apply-sysctl]"
    exit 1
}

errmsg() { echo "[ERROR] $*" >&2; }

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
        --gateway)
            GATEWAY="$2"
            shift 2
            ;;
        --no-mtu)
            NO_MTU=true
            shift
            ;;
        --renderer)
            RENDERER="$2"
            shift 2
            ;;
        --apply-sysctl)
            APPLY_SYSCTL=true
            shift
            ;;
        *)
            errmsg "Unknown argument: $1"
            usage
            ;;
    esac
done

[[ ${#NIC_LIST[@]} -lt 1 ]] && { errmsg "At least one NIC must be specified"; usage; }

# Functions
get_ip_for_nic() { ip -4 addr show "$1" | awk '/inet / {print $2}' | head -n1; }

get_local_subnet() {
    local nic="$1"
    subnet=$(ip -o -f inet route show dev "$nic" scope link | awk '{print $1}' | head -n1)
    if [[ -z "$subnet" ]]; then
        ip_only=$(get_ip_for_nic "$nic")
        subnet="${ip_only%/*}/24"
        echo "⚠️ Could not determine network CIDR for $nic, defaulting to $subnet"
    fi
    echo "$subnet"
}

# --- Generate Netplan YAML ---
echo "network:" > "$OUTPUT_FILE"
echo "  version: 2" >> "$OUTPUT_FILE"
echo "  renderer: $RENDERER" >> "$OUTPUT_FILE"
echo "  ethernets:" >> "$OUTPUT_FILE"

table_id=$START_TABLE

for nic in "${NIC_LIST[@]}"; do
    ip_cidr=$(get_ip_for_nic "$nic")
    [[ -z "$ip_cidr" ]] && { errmsg "No IP address found for $nic"; exit 1; }

    ip_only="${ip_cidr%%/*}"
    local_subnet=$(get_local_subnet "$nic")

    echo "    $nic:" >> "$OUTPUT_FILE"
    echo "      dhcp4: no" >> "$OUTPUT_FILE"
    [[ $NO_MTU == false ]] && echo "      mtu: $MTU" >> "$OUTPUT_FILE"
    echo "      addresses:" >> "$OUTPUT_FILE"
    echo "        - $ip_cidr" >> "$OUTPUT_FILE"

    echo "      routes:" >> "$OUTPUT_FILE"
    # Local subnet: link-scoped, no via
    echo "        - to: $local_subnet" >> "$OUTPUT_FILE"
    echo "          table: $table_id" >> "$OUTPUT_FILE"

    # Default route if gateway specified
    if [[ -n "$GATEWAY" ]]; then
        echo "        - to: 0.0.0.0/0" >> "$OUTPUT_FILE"
        echo "          via: $GATEWAY" >> "$OUTPUT_FILE"
        echo "          table: $table_id" >> "$OUTPUT_FILE"
    fi

    # Routing policy for SBR
    echo "      routing-policy:" >> "$OUTPUT_FILE"
    echo "        - from: $ip_only" >> "$OUTPUT_FILE"
    echo "          table: $table_id" >> "$OUTPUT_FILE"

    echo "      ignore-carrier: true" >> "$OUTPUT_FILE"

    ((table_id++))
done

echo "✅ Netplan file generated at $OUTPUT_FILE (review before applying)"

# --- Generate sysctl file ---
: > "$SYSCTL_FILE"
echo "kernel.numa_balancing=0" >> "$SYSCTL_FILE"

for nic in "${NIC_LIST[@]}"; do
    echo "net.ipv4.conf.${nic}.arp_filter = 1" >> "$SYSCTL_FILE"
    echo "net.ipv4.conf.${nic}.arp_ignore = 1" >> "$SYSCTL_FILE"
    echo "net.ipv4.conf.${nic}.arp_announce = 2" >> "$SYSCTL_FILE"
done

if $APPLY_SYSCTL; then
    sysctl --system
    echo "✅ Sysctl applied immediately"
else
    echo "✅ Sysctl file generated: $SYSCTL_FILE (review. copy to /etc/sysctl.d and apply with 'sudo sysctl --system')"
fi

