#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that Weka cached LIDs match OS reported LIDs"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-422897"
WTA_REFERENCE=""
RETURN_CODE=0

# Background notes:
#  Issue: If the subnet manager (SM) should issue new LIDs to the WEKA backends,
#   it is possible for the OS to have the new LID, but WEKA to have a cached (old)
#   LID. When this occurs, no Infiniband clients will to be able to mount
#   the cluster.

#  Mitigation: Restart the affected containers.

#  Code fix: The fix for this issue is WEKAPP-422897, but as of 2025-02-06, this
#   fix is not part of any GA WEKA release.


declare -A NIC_LIDS

# Is the cluster using a NIC over Infiniband?
while read CONTAINER; do
    while read NET_ENTRY; do
        if [[ ${NET_ENTRY} =~ "name:"([^.]*) ]]; then
            NET_NAME=${BASH_REMATCH[1]}
            if [[ $(cat /sys/class/net/${NET_NAME}/type) == 32 ]]; then
                IB_INTERFACE=${NET_NAME}
                # I don't know if this check is sufficient in all configurations
                LOCAL_LID=$(cat /sys/class/net/${IB_INTERFACE}/device/infiniband/*/ports/*/lid 2>/dev/null)
                LOCAL_LID=$(printf "%d" ${LOCAL_LID})
                NIC_LIDS[${IB_INTERFACE}]=${LOCAL_LID}
            fi
        fi
    done < <(weka local resources -C ${CONTAINER} net --stable -J | grep -w -e name | tr -d \"\,[:blank:])
done < <(weka local ps --output name --no-header | awk '/compute|drive|frontend/')


# If there are Infiniband NICs in use by WEKA, compare the LIDs
if [[ -n ${!NIC_LIDS[@]} ]]; then
    for NIC in ${!NIC_LIDS[@]}; do
        while read WEKA_CONTAINER WEKA_CONTAINER_PORT; do
            MANHOLE=$(weka debug manhole -P ${WEKA_CONTAINER_PORT} -T 5s --slot 1 network_get_dpdk_ports | grep -E '(netdevName|lid)' | paste - - | grep ${NIC} | tr -d '[:space:]' | sed 's/"//g')
            if [[ ${MANHOLE} =~ lid:([[:digit:]]+) ]]; then
                WEKA_LID=${BASH_REMATCH[1]}
                if [[ ${NIC_LIDS[${NIC}]} != ${WEKA_LID} ]]; then
                    echo "WARN: ${NIC} reports LID ${NIC_LIDS[${NIC}]} but WEKA container ${WEKA_CONTAINER} reports LID ${WEKA_LID}"
                    RETURN_CODE=254
                fi
            fi
        done < <(weka local ps --output name,port --no-header | awk '/compute|drive|frontend/')
    done
fi


if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No Infiniband LID mismatches detected."
else
    echo "Recommended Resolution: restart WEKA containers on affected backends."
fi

exit ${RETURN_CODE}
