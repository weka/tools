#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for optimal Mellanox NIC settings"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-524442"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2026-09-10
# k8s-client variant: does not use the weka CLI. Every ConnectX adapter that
# mst reports is checked, rather than only those assigned to WEKA containers.

if ! mst version &> /dev/null; then
    echo "Unable to locate mst; skipping mlxconfig checks."
    exit 0
elif ! mlxconfig -v &> /dev/null; then
    echo "Unable to locate mlxconfig; skipping mlxconfig checks."
    exit 0
fi

mst start &> /dev/null

# mst status -v columns: DEVICE_TYPE  MST  PCI  RDMA  NET  NUMA
declare -A MST_DEVICES
while read -r MST_DEV NET_NAME; do
    MST_DEVICES[${MST_DEV}]=${NET_NAME#net-}
done < <(mst status -v 2>/dev/null | awk '/ConnectX/{print $2, $5}')

if [[ ${#MST_DEVICES[@]} -gt 0 ]]; then
    if ! grep -q "^ib_uverbs .*Live" /proc/modules ; then
        RETURN_CODE=254
        echo "The kernel module ib_uverbs has not been loaded. Suggest checking kernel module versions and/or OFED"
        echo "This module is required to successfully use Mellanox cards - refer to WEKAPP-524442 for details"
    fi
    for MST_DEV in "${!MST_DEVICES[@]}"; do
        NET_NAME=${MST_DEVICES[${MST_DEV}]}
        MLXCONFIG_OUTPUT=$(mlxconfig -d "${MST_DEV}" q 2>/dev/null)
        if echo "${MLXCONFIG_OUTPUT}" | grep -q 'PCI_WR_ORDERING.*(0)'; then
            RETURN_CODE=254
            echo "PCI_WR_ORDERING set to 0 on ${NET_NAME} (${MST_DEV}) - recommended value is 1."
        fi
        if echo "${MLXCONFIG_OUTPUT}" | grep -q 'ADVANCED_PCI_SETTINGS.*(0)'; then
            RETURN_CODE=254
            echo "ADVANCED_PCI_SETTINGS set to 0 on ${NET_NAME} (${MST_DEV}) - recommended value is 1."
        fi
    done
else
    echo "No ConnectX adapters reported by mst."
fi

# Check that all Infiniband devices have a mode=datagram
for NET_DEVICE_PATH in /sys/class/net/* ; do
    NET_DEVICE=${NET_DEVICE_PATH##*/}
    if [[ ! -e ${NET_DEVICE_PATH}/type ]] ; then
        continue
    fi
    if [[ "$(cat ${NET_DEVICE_PATH}/type)" != "32" ]] ; then
        continue
    fi
    if [[ ! -e ${NET_DEVICE_PATH}/mode ]] ; then
        RETURN_CODE=254
        echo "No mode file exists for Infiniband device ${NET_DEVICE}: ${NET_DEVICE_PATH}/mode does not exist, so cannot determine if it's datagram or connected"
        echo "Recommended resolution: upgrade the Infiniband device driver"
        continue
    fi
    if [[ "$(cat ${NET_DEVICE_PATH}/mode)" != "datagram" ]] ; then
        RETURN_CODE=254
        echo "The connection mode for Infiniband device ${NET_DEVICE} according to ${NET_DEVICE_PATH}/mode is not datagram"
        echo "Recommended resolution: ensure the Infiniband device is in datagram mode"
        continue
    fi
done

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Mellanox NIC settings correctly set."
else
    echo "Mellanox NIC settings are not as recommended. Recommended Resolution:"
    echo 'for dev in $(ls /sys/class/infiniband/); do sudo mlxconfig -y -d ${dev} set ADVANCED_PCI_SETTINGS=1 PCI_WR_ORDERING=1 ; done'
    echo "Followed by rebooting this host, one at a time"
fi

exit $RETURN_CODE
