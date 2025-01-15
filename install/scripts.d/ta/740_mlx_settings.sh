#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for optimal Mellanox NIC settings"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

declare -A PCI_BUSES

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    exit 254
elif [[ $? -eq 127 ]]; then
    echo "WEKA not found"
    exit 254
elif [[ $? -eq 41 ]]; then
    echo "Unable to login into Weka cluster."
    exit 254
fi

if ! mst version &> /dev/null; then
    echo "Unable to locate mst."
    exit 0
elif ! mlxconfig -v &> /dev/null; then
    echo "Unable to locate mlxconfig."
    exit 0
elif ! lshw -version &> /dev/null; then
    echo "Unable to locate lshw."
    exit 0
fi

# Look for ConnectX adapters by iterating over each container
while read CONTAINER; do
    while read PCI; do
        while read NET; do
            PCI_BUSES[$PCI]=$NET
        done < <(lshw -C network -businfo -quiet | awk '/'"$PCI"'/ && /ConnectX/{print $2}')
    done < <(weka local resources net -C "$CONTAINER" --stable | awk 'NR>1 {print $2}')
done < <(weka local ps --no-header -o name)

if [[ ${#PCI_BUSES[@]} -gt 0 ]]; then
    mst start &> /dev/null
    for PCI in "${!PCI_BUSES[@]}"; do
        if [[ -n ${PCI_BUSES[$PCI]} ]]; then
            while read DEV; do
                if mlxconfig -d "$DEV" q | awk '/PCI_WR_ORDERING/ && /(0)/' &> /dev/null; then
                    RETURN_CODE=254
                    echo "PCI_WR_ORDERING set to 0 on ${PCI_BUSES[$PCI]} - recommended value is 1."
                fi
                if mlxconfig -d "$DEV" q | awk '/ADVANCED_PCI_SETTINGS/ && /(0)/' &> /dev/null; then
                    RETURN_CODE=254
                    echo "ADVANCED_PCI_SETTINGS set to 0 on ${PCI_BUSES[$PCI]} - recommended value is 1."
                fi
            done < <(mst status -v | awk '/'"${PCI_BUSES[$PCI]}"'/{print $2}')
        fi
    done
    mst stop &> /dev/null
fi

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Mellanox NIC settings correctly set."
else
    echo "Mellanox NIC settings are not as recommended. Recommended Resolution:"
    echo 'for dev in $(ls /sys/class/infiniband/); do sudo mlxconfig -y -d ${dev} set ADVANCED_PCI_SETTINGS=1 PCI_WR_ORDERING=1 ; done'
    echo "Followed by rebooting this host, one at a time"
fi

exit $RETURN_CODE
