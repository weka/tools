#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Hashing on DPDK LACP links is only supported on CX6-DX and higher"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-429344"
WTA_REFERENCE=""
RETURN_CODE=0

declare -A NET_MODEL
declare -A PCI_BUSES

BONDED_INTERFACE=""

# The below is currently unverified:
#  In order to enable this feature, set this mode for both bonded devices through
#  the below sysfs before the device is in switchdev mode:
#  echo "hash" > /sys/class/net/enp8s0f0/compat/devlink/lag_port_select_mode

#  This feature requires to set LAG_RESOURCE_ALLOCATION to 1 with mlxconfig

# References:
#  https://download.lenovo.com/servers/mig/2023/06/12/57746/mlnx-lnvgy_dd_nic_cx.ib-5.9-0.5.6.0-0_rhel8_x86-64.pdf


# dmesg may indicate 'devlink op lag_port_select_mode doesn't support hw lag'
#  on unsupported models.

if ! lshw -version &> /dev/null; then
    echo "Unable to locate lshw."
    exit 0
fi

# weka local resources net -C drives0 --stable
# NET DEVICE  IDENTIFIER    DEFAULT GATEWAY  IPS  NETMASK  NETWORK LABEL
# bond0       0000:08:00.0

# lshw -C network -businfo
# Bus info          Device           Class          Description
# =============================================================
# pci@0000:65:00.0  ens9f0np0        network        MT2892 Family [ConnectX-6 Dx]
# pci@0000:65:00.1  ens9f1np1        network        MT2892 Family [ConnectX-6 Dx]


# Is the cluster using a bonded NIC?
while read CONTAINER; do
    while read NET_ENTRY; do
        if [[ ${NET_ENTRY} =~ "name:"(.*) ]]; then
            NET_NAME=${BASH_REMATCH[1]}
            if [[ -f /proc/net/bonding/${NET_NAME} ]]; then
                BONDED_INTERFACE=${NET_NAME}
            fi
        fi
    done < <(weka local resources -C ${CONTAINER} net --stable -J | grep -w -e name | tr -d \"\,[:blank:])
done < <(weka local ps --output name --no-header | grep -vw -e envoy -e ganesha -e samba -e smbw -e s3)


if [[ -n ${BONDED_INTERFACE} ]]; then
    if [[ $(cat /sys/class/net/${BONDED_INTERFACE}/bonding/xmit_hash_policy) =~ "layer2" ]]; then
        echo "WARN: xmit hash policy for ${BONDED_INTERFACE} set to layer2."
    fi

    # Look for ConnectX adapters by iterating over each container
    while read CONTAINER; do
        while read PCI; do
            while read LINE; do
                if [[ $LINE =~ "pci@"([[:digit:][:punct:]]+)[[:blank:]]+([[:alnum:]]+)[[:blank:]]+"network"[[:blank:]]+(.*) ]]; then
                    NET=${BASH_REMATCH[2]}
                    MODEL=${BASH_REMATCH[3]}
                    PCI_BUSES[$PCI]=${NET}
                    NET_MODEL[$NET]=${MODEL}
                fi
            done < <(lshw -C network -businfo -quiet | awk '/'"$PCI"'/ && /ConnectX/{print $0}')
        done < <(weka local resources net -C "$CONTAINER" --stable | awk 'NR>1 {print $2}' | sed -e 's/\.[0-9]//g')
    done < <(weka local ps --output name --no-header | grep -vw -e envoy -e ganesha -e samba -e smbw -e s3)
else
    echo "INFO: NIC bonding not enabled."
    exit 0
fi


if [[ ${#PCI_BUSES[@]} -eq 0 ]]; then
    echo "INFO: Unable to locate Mellanox NICs."
    exit 0
elif [[ ${#PCI_BUSES[@]} -gt 1 ]]; then
    echo "WARN: Potentially bonding across NICs, which is not supported."
    RETURN_CODE=254
else
    for NET in "${!NET_MODEL[@]}"; do
        if [[ ! ((${NET_MODEL[${NET}]} =~ "ConnectX-6 Dx") || (${NET_MODEL[${NET}]} =~ "ConnectX-7")) ]]; then
            echo "WARN: The ${NET} NIC (${NET_MODEL[${NET}]}) may not support hashing on bonded links."
            RETURN_CODE=254
        fi
    done
fi


if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Bonding properly configured."
else
    echo "Recommended Resolution: Determine NIC compatibility with the bonding mode selected:"
    echo "https://docs.weka.io/planning-and-installation/prerequisites-and-compatibility#networking-ethernet"
fi

exit ${RETURN_CODE}
