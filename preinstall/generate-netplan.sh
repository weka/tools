#!/usr/bin/env bash
#
# generate-netplan.sh
#
# Generates a Netplan YAML file for multiple NICs with static routing tables and SBR rules.
#
# Features:
# - Discovers IP/subnet for each NIC.
# - If --gateway is specified, adds a default route (0.0.0.0/0) in each NIC’s table.
# - Both default and local subnet routes include “from:” to set the source IP.
# - Optional --floating-ips adds virtual/floating IP routing-policy entries (shared by all NICs).
# - Optional --no-mtu disables MTU=9000 setting.
# - Also generates a sysctl file with ARP tuning and kernel.numa_balancing=0.
#   * By default, only generates the file for review.
#   * If --apply-sysctl is given, applies it immediately.
# - Netplan file is generated but NOT applied automatically.
# - Table IDs start from 101.
#
# Example:
#   ./generate-netplan.sh --nics ens19 ens20 --gateway 10.0.255.254
#   ./generate-netplan.sh --nics ens19 ens20 --gateway 10.0.255.254 --floating-ips "10.0.1.100,10.0.1.101" --no-mtu --apply-sysctl
#

set -euo pipefail

# --- Defaults ---
NETPLAN_FILE="99-weka-netplan.yaml"
SYSCTL_FILE="99-weka-sysctl.conf"
START_TABLE_ID=101
NO_MTU=false
APPLY_SYSCTL=false
FLOATING_IPS=()

# --- Parse Args ---
NICS=()
GATEWAY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --nics)
      shift
      while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
        NICS+=("$1")
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
    --apply-sysctl)
      APPLY_SYSCTL=true
      shift
      ;;
    --floating-ips)
      IFS=',' read -ra FLOATING_IPS <<< "$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ ${#NICS[@]} -eq 0 ]]; then
  echo "No NICs specified. Use --nics <nic1> <nic2> ..."
  exit 1
fi

# --- Start building Netplan YAML ---
echo "network:" > "$NETPLAN_FILE"
echo "  version: 2" >> "$NETPLAN_FILE"
echo "  renderer: networkd" >> "$NETPLAN_FILE"
echo "  ethernets:" >> "$NETPLAN_FILE"

table_id=$START_TABLE_ID

for nic in "${NICS[@]}"; do
  ip_with_mask=$(ip -4 -o addr show dev "$nic" | awk '{print $4}')
  ip_only=$(echo "$ip_with_mask" | cut -d'/' -f1)
  mask_bits=$(echo "$ip_with_mask" | cut -d'/' -f2)

  if [[ -z "$ip_with_mask" ]]; then
    echo " Could not determine IP for $nic, skipping."
    continue
  fi

  # Derive subnet network address without ipcalc
  network=$(ip -4 route show dev "$nic" | awk '/proto kernel/ {print $1; exit}')
  if [[ -z "$network" ]]; then
    echo " Could not determine network from $ip_with_mask, defaulting to /24"
    network="$(echo "$ip_only" | cut -d'.' -f1-3).0/24"
  fi

  echo "    $nic:" >> "$NETPLAN_FILE"
  echo "      dhcp4: no" >> "$NETPLAN_FILE"
  if [[ $NO_MTU == false ]]; then
    echo "      mtu: 9000" >> "$NETPLAN_FILE"
  fi
  echo "      addresses:" >> "$NETPLAN_FILE"
  echo "        - $ip_with_mask" >> "$NETPLAN_FILE"
  echo "      routes:" >> "$NETPLAN_FILE"
  echo "        - to: $network" >> "$NETPLAN_FILE"
  echo "          from: $ip_only" >> "$NETPLAN_FILE"
  echo "          table: $table_id" >> "$NETPLAN_FILE"

  if [[ -n "$GATEWAY" ]]; then
    # Add default route with “from” and “via”
    echo "        - to: 0.0.0.0/0" >> "$NETPLAN_FILE"
    echo "          from: $ip_only" >> "$NETPLAN_FILE"
    echo "          via: $GATEWAY" >> "$NETPLAN_FILE"
    echo "          table: $table_id" >> "$NETPLAN_FILE"
  fi

  echo "      routing-policy:" >> "$NETPLAN_FILE"
  echo "        - from: $ip_only" >> "$NETPLAN_FILE"
  echo "          table: $table_id" >> "$NETPLAN_FILE"
  echo "          priority: $table_id" >> "$NETPLAN_FILE"

  # Add floating IPs if specified
  if [[ ${#FLOATING_IPS[@]} -gt 0 ]]; then
    echo "        # Floating IPs" >> "$NETPLAN_FILE"
    priority=201
    for fip in "${FLOATING_IPS[@]}"; do
      echo "        - from: $fip" >> "$NETPLAN_FILE"
      echo "          table: $table_id" >> "$NETPLAN_FILE"
      echo "          priority: $priority" >> "$NETPLAN_FILE"
      ((priority++))
    done
  fi

  echo "      ignore-carrier: true" >> "$NETPLAN_FILE"

  ((table_id++))
done

echo "Netplan file generated: $NETPLAN_FILE (review before applying)"
echo

# --- Generate sysctl file ---
cat > "$SYSCTL_FILE" <<EOF
# Weka system tuning
kernel.numa_balancing=0
net.ipv4.conf.all.arp_ignore=1
net.ipv4.conf.all.arp_announce=2
net.ipv4.conf.default.arp_ignore=1
net.ipv4.conf.default.arp_announce=2
EOF

if [[ "$APPLY_SYSCTL" == true ]]; then
  echo " Applying sysctl settings..."
  sysctl -p "$SYSCTL_FILE"
else
  echo "Sysctl file generated: $SYSCTL_FILE (review. Copy to /etc/sysctl.d and apply with 'sudo sysctl --system')"
fi

