#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="NFSW FIPs sanity"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

# Check if we can run weka commands
if ! weka status &> /dev/null; then
    echo "ERROR: Not able to run weka commands"
    exit 254
fi

case $? in
    127)
        echo "WEKA not found"
        exit 254
        ;;
    41)
        echo "Unable to login to Weka cluster."
        exit 254
        ;;
esac

CONTAINER_ID=$(weka cluster container -F hostname=$(hostname),container=frontend0 --no-header -o id)
PROCESS_ID=$(weka cluster process -F hostname=$(hostname),container=frontend0,role=frontend --no-header -o id | head -n1)

# Only perform these checks from those hosts that are part of an NFS interface group
while read FIP_IP FIP_HOST_LABEL FIP_HOST FIP_INTERFACE; do

    #############################
    # LOCAL FIP EXISTENCE CHECK #
    #############################
    if ip addr show dev ${FIP_INTERFACE} | grep -q ${FIP_IP}; then

        FIP_MAC=$(ip addr show dev ${FIP_INTERFACE} | grep -oE '([[:xdigit:]]{2}[:]){5}[[:xdigit:]]{2}' | head -n1)
        if [[ -n ${FIP_MAC} ]]; then

            ###################
            # ARP CACHE CHECK #
            ###################
            FIP_MAC_ARP=$(ip neigh | grep ${FIP_IP} | awk '{print $5}')

            if [[ -n ${FIP_MAC_ARP} ]]; then
                if [[ ${FIP_MAC,,} != ${FIP_MAC_ARP,,} ]]; then
                    echo "WARN: FIP ${FIP_IP} on interface with MAC ${FIP_MAC}, but also ${FIP_MAC_ARP} in arp cache"
                    RETURN_CODE=254
                fi
            fi

            ################
            # ARPING CHECK #
            ################
            if which arping &>/dev/null; then
                if strings $(which arping) | grep -q iputils; then
                    FIP_MAC_ARP=$(arping -I ${FIP_INTERFACE} -c 5 -w 5 ${FIP_IP} | grep -m 1 -oE '([[:xdigit:]]{2}[:]){5}[[:xdigit:]]{2}')
            
                # The "other" arping? https://github.com/ThomasHabets/arping
                else
                    FIP_MAC_ARP=$(arping -i ${FIP_INTERFACE} -c 5 ${FIP_IP} | grep -m 1 -oE '([[:xdigit:]]{2}[:]){5}[[:xdigit:]]{2}')
                fi

                if [[ -n ${FIP_MAC_ARP} ]]; then
                    if [[ ${FIP_MAC,,} != ${FIP_MAC_ARP,,} ]]; then
                        echo "WARN: FIP ${FIP_IP} on interface with MAC ${FIP_MAC}, but also ${FIP_MAC_ARP} in arp cache"
                        RETURN_CODE=254
                    fi
                fi                

            else
                echo "INFO: arping not installed"
            fi
        fi
    else
        echo "WARN: Unable to locate FIP ${FIP_IP} on interface ${FIP_INTERFACE}"
        RETURN_CODE=254
    fi
done < <(weka nfs interface-group assignment --no-header -o ip,host,port | awk -v container_id="${CONTAINER_ID}" '$3 == container_id')


# Comparing the local state and cluster state tables is too difficult without jq
if jq --version &> /dev/null; then
    while read FIP_IP FIP_STALE FIP_STATUS; do
        # Only care about entries in "OK" status?
        if [[ ${FIP_STATUS} == "OK" ]]; then
            # Does the FIP exist on a local interface?
            if ip addr show | grep -q ${FIP_IP}; then
                # Does the FIP appear in the global table for this host?
                if ! weka debug manhole get_aggregated_cluster_status table_names="floatingIps" --node $(weka cluster process -L --no-header -o id) | jq -cr '(.floatingIps|to_entries[]|[.key, (.value|.isStale,.status,.serial.sourceNodeId)])|@tsv' | awk '/OK/ && /NodeId<${PROCESS_ID}>/'; then
                    echo "WARN: Global state FIP ${FIP_IP} not found for process ${PROCESS_ID}"
                    RETURN_CODE=254
                fi
            else
                echo "WARN: Local state FIP ${FIP_IP} not assigned to interface"
                RETURN_CODE=254
            fi
        fi
    done < <(weka debug manhole get_localstate table_names="floatingIps" -n ${PROCESS_ID} | jq -cr '(.floatingIps|to_entries[]|[.key, (.value|.isStale,.status)])|@tsv')
fi


if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "NFSW FIPs sanity check passed."
fi

exit ${RETURN_CODE}
