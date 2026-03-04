#!/bin/bash
set -euo pipefail  # fail on error, unset var, and pipeline errors

DESCRIPTION="Bonding sanity check"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-539450"
RETURN_CODE=0

# WEKAPP-539450
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
#  -On the WEKA side, enabling DevX-level control by enabling HAVE_MLX5DV_DR_ACTION_DEST_DEVX_TIR, restored LACP and hash-based distribution on CX6-DX and newer (not effecting the behavior of older nics).
#  -Changing lag_port_select_mode to queue_affinity again breaks LACP for those nics, and the bond is treated as a single port.


# Version comparison functions
verlte() { [ "$1" = "$(printf "%s\n%s" "$1" "$2" | sort -V | head -n1)" ]; }
verlt()  { [ "$1" = "$2" ] && return 1 || verlte "$1" "$2"; }

CURRENT_WEKA_VERSION=$(weka version current)
VIRTUAL_BOND_FOUND=0
BOND_INTERFACE=""

# Iterate over compute/frontend/drive containers
mapfile -t CONTAINERS < <(weka local ps --output name --no-header | grep -E 'compute|drive|frontend')

for CONTAINER in "${CONTAINERS[@]}"; do
    # Get network interfaces for container
    mapfile -t NET_ENTRIES < <(weka local resources -C "$CONTAINER" net --stable -J | grep -w 'name' | tr -d '" ,[:blank:]')
    for NET_ENTRY in "${NET_ENTRIES[@]}"; do
        if [[ "$NET_ENTRY" =~ name:(.*) ]]; then
            NET_NAME="${BASH_REMATCH[1]}"
            if [[ -f "/proc/net/bonding/$NET_NAME" ]]; then
                BOND_INTERFACE="$NET_NAME"
                read -r _ BOND_MODE < "/sys/class/net/${BOND_INTERFACE}/bonding/mode"
            fi
        fi
    done
done

if [[ -n "$BOND_INTERFACE" ]]; then
    # Version checks
    if verlt "4.3.3" "$CURRENT_WEKA_VERSION"; then
        :
    elif [[ "$CURRENT_WEKA_VERSION" == 4.* ]]; then
        if verlt "$CURRENT_WEKA_VERSION" "4.4.10.183"; then
            echo "WARN: This cluster does not contain the fixes from ${JIRA_REFERENCE}."
            echo " This could lead to unexpected loss of connectivity, particularly during link loss."
            RETURN_CODE=254
        fi

    elif [[ "$CURRENT_WEKA_VERSION" == 5.* ]]; then
        if verlt "$CURRENT_WEKA_VERSION" "5.1.0"; then
            echo "WARN: This cluster does not contain the fixes from ${JIRA_REFERENCE}."
            echo " This could lead to unexpected loss of connectivity, particularly during link loss."
            RETURN_CODE=254
        fi
    fi

    # Bonding mode check (1=active-backup, 4=LACP)
    if [[ "$BOND_MODE" != "1" && "$BOND_MODE" != "4" ]]; then
        echo "WARN: bond mode $BOND_MODE is not supported by WEKA -- only 1 (active-backup) and 4 (LACP)"
        RETURN_CODE=254
    fi

    # Xmit hash policy check
    HASH_POLICY=$(<"/sys/class/net/${BOND_INTERFACE}/bonding/xmit_hash_policy")
    if [[ "$HASH_POLICY" =~ layer2 ]]; then
        echo "WARN: xmit hash policy for ${BOND_INTERFACE} set to layer2."
        RETURN_CODE=254
    fi

    # Iterate over slave links
    read -ra SLAVE_LINKS < "/sys/class/net/${BOND_INTERFACE}/bonding/slaves"
    for SLAVE_LINK in "${SLAVE_LINKS[@]}"; do
        # Check for virtual bond device
        IB_PATH=$(readlink -f "/sys/class/net/${SLAVE_LINK}/device/infiniband/" || true)
        if [[ "$IB_PATH" =~ bond ]]; then
            VIRTUAL_BOND_FOUND=1
        fi

        # NIC model detection (Only CX-6 DX and CX-7 are supported per docs)
        PCI_DEV=$(basename "$(readlink -f "/sys/class/net/${SLAVE_LINK}/device")")
        PRODUCT_NAME=$(lspci -s "$PCI_DEV" -vv 2>/dev/null | grep "Product Name" || true)
        if [[ "$PRODUCT_NAME" =~ "Socket Direct" ]]; then
            echo "WARN: Socket Direct NICs (${SLAVE_LINK}) are unlikely to support bonding."
            RETURN_CODE=254
        elif [[ ! "$PRODUCT_NAME" =~ "ConnectX-6 Dx|ConnectX-7" ]]; then
            echo "WARN: Only ConnectX-6 Dx and ConnectX-7 are officially supported for bonding."
            RETURN_CODE=254
        fi
    done

    if [[ $VIRTUAL_BOND_FOUND -eq 0 ]]; then # WEKAPP-571692
        echo "WARN: virtual bond device not located under /sys/class/infiniband/"
        echo " Check that MOFED is properly installed and the adapter is supported."
        RETURN_CODE=254
    fi
fi

# Final output
if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Bonding properly configured."
else
    echo "Recommended Resolution: Determine NIC compatibility with the bonding mode selected:"
    echo "https://docs.weka.io/planning-and-installation/prerequisites-and-compatibility#networking-ethernet"
fi

exit $RETURN_CODE
