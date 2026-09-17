#!/bin/bash
set -euo pipefail  # fail on error, unset var, and pipeline errors

DESCRIPTION="Bonding sanity check"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-539450"
RETURN_CODE=0

# Last modified: 2026-09-10
# k8s-client variant: does not use the weka CLI. Every bond on the host is
# checked, and the WEKA-version check for WEKAPP-539450 is omitted; ensure the
# cluster the client joins is at 4.4.10.183+ or 5.1.0+ if bonding is used.

# https://www.notion.so/wekaio/LACP-CX6-DX-and-newer-2a030b0d101c8048a9bbc587e0242f87#2a330b0d101c80cbbbe9e689f0e7982f
# CX-6 and older adapters (WARNING: not officially supported for bonding)
#  -Use the Verbs path
#  -Support only queue-affinity mode (file lag_port_select_mode cannot be changed)
# CX-6 LX (WARNING: not officially supported for bonding)
#  -Uses Verbs path
#  -Default lag_port_select_mode is hash
#  -Changing to queue_affinity reverts to round-robin queue affinity
# CX-6 DX and newer
#  -Require DevX-level control (not available via Verbs API)
#  -Legacy mode hardware LAG is broken, the bond is treated as a single port
#  -Changing lag_port_select_mode to queue_affinity breaks LACP for those nics, and the bond is treated as a single port.

# Discover bonds via their sysfs bonding directory
BONDS=""
for BONDING_DIR in /sys/class/net/*/bonding; do
    [[ -d "$BONDING_DIR" ]] || continue
    BONDS+=" $(basename "$(dirname "$BONDING_DIR")")"
done

if [[ -z "${BONDS}" ]]; then
    echo "No bond interfaces found."
    exit 0
fi

for BOND_INTERFACE in ${BONDS}; do
    VIRTUAL_BOND_FOUND=0
    read -r _ BOND_MODE < "/sys/class/net/${BOND_INTERFACE}/bonding/mode"

    # Bonding mode check (1=active-backup, 4=LACP)
    if [[ "$BOND_MODE" != "1" && "$BOND_MODE" != "4" ]]; then
        echo "WARN: ${BOND_INTERFACE} bond mode $BOND_MODE is not supported by WEKA -- only 1 (active-backup) and 4 (LACP)"
        RETURN_CODE=254
    fi

    # Xmit hash policy check -- only meaningful for LACP; active-backup uses a
    # single member at a time and defaults to layer2.
    if [[ "$BOND_MODE" == "4" ]]; then
        read -r HASH_POLICY _ < "/sys/class/net/${BOND_INTERFACE}/bonding/xmit_hash_policy"
        if [[ "$HASH_POLICY" == "layer2" ]]; then
            echo "WARN: xmit hash policy for ${BOND_INTERFACE} is ${HASH_POLICY} -- traffic will not spread across bond members."
            RETURN_CODE=254
        fi
    fi

    # Iterate over bond members ("slaves" is the kernel's sysfs name)
    MEMBER_LINKS=()
    read -ra MEMBER_LINKS < "/sys/class/net/${BOND_INTERFACE}/bonding/slaves" || true
    if [[ ${#MEMBER_LINKS[@]} -eq 0 ]]; then
        echo "WARN: ${BOND_INTERFACE} has no member interfaces."
        RETURN_CODE=254
        continue
    fi

    for MEMBER_LINK in "${MEMBER_LINKS[@]}"; do
        # Check for virtual bond device. The hardware LAG device is an entry
        # (mlx5_bond_N) inside the member's infiniband directory, not part of
        # the directory's own path.
        for IB_DEV in "/sys/class/net/${MEMBER_LINK}/device/infiniband/"*; do
            [[ -e "$IB_DEV" ]] || continue
            if [[ "${IB_DEV##*/}" =~ bond ]]; then
                VIRTUAL_BOND_FOUND=1
            fi
        done

        # NIC model detection (Only CX-6 DX and CX-7 are supported per docs)
        PCI_DEV=$(basename "$(readlink -f "/sys/class/net/${MEMBER_LINK}/device")")
        PRODUCT_NAME=$(lspci -s "$PCI_DEV" -vv 2>/dev/null | grep "Product Name" || true)
        if [[ "$PRODUCT_NAME" =~ "Socket Direct" ]]; then
            echo "WARN: Socket Direct NICs (${MEMBER_LINK}) are unlikely to support bonding."
            RETURN_CODE=254
        elif [[ ! "$PRODUCT_NAME" =~ (ConnectX-6\ Dx|ConnectX-7) ]]; then
            echo "WARN: ${MEMBER_LINK} in ${BOND_INTERFACE}: only ConnectX-6 Dx and ConnectX-7 are officially supported for bonding."
            RETURN_CODE=254
        fi
    done

    if [[ $VIRTUAL_BOND_FOUND -eq 0 ]]; then # WEKAPP-571692
        echo "WARN: no virtual bond device (mlx5_bond_*) found for any member of ${BOND_INTERFACE}"
        echo " Check that MOFED is properly installed and the adapter is supported."
        RETURN_CODE=254
    fi
done

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Bonding properly configured."
else
    echo "Recommended Resolution: Determine NIC compatibility with the bonding mode selected:"
    echo "https://docs.weka.io/planning-and-installation/prerequisites-and-compatibility#networking-ethernet"
fi

exit $RETURN_CODE
