#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if each Weka dataplane NIC has a corresponding, valid, management IP"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header | grep -e compute -e drives -e frontend); do
    NET_NAME=""
    NET_COUNT=0
    SINGLE_IP=0

    while read NET_ENTRY; do
        if [[ ${NET_ENTRY} =~ "name:"(.*) ]]; then
            NET_NAME=${BASH_REMATCH[1]}
        fi
        if [[ ${NET_ENTRY} =~ "ips:[]" ]]; then
            SINGLE_IP=1
        fi

        if [[ -n ${NET_NAME} ]]; then
            NET_COUNT=$((NET_COUNT+1))

            if [[ $(ip -4 -j -o addr show dev ${NET_NAME} 2>/dev/null | tr -d \"\[:blank:]) =~ "local:"([0-9\.]+) ]]; then
                NET_IP=${BASH_REMATCH[1]}
                MATCH_FOUND=0
                for IP in $(weka local resources -C ${WEKA_CONTAINER} --stable | grep -e ^"Management IPs" | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+\.[0-9]\+"); do
                    if [[ "${IP}" == "${NET_IP}" ]]; then
                        MATCH_FOUND=1
                        break
                    fi
                done
                if [[ ${MATCH_FOUND} -eq 0 ]]; then
                    echo "WARN: Dataplane NIC ${NET_NAME} has IP ${NET_IP}, but this does not appear in the ${WEKA_CONTAINER} container's resources"
                    RETURN_CODE=254
                fi
            fi
        fi
    done < <(weka local resources -C ${WEKA_CONTAINER} net --stable -J | grep -w -e name -e ips | paste - - | tr -d \"\,[:blank:])

    MGMT_IP_COUNT=$(weka local resources -C ${WEKA_CONTAINER} --stable | grep -e ^"Management IPs" | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+\.[0-9]\+" | wc -l)
    if [[ ${SINGLE_IP} -eq 1 ]] && [[ ${NET_COUNT} -ne ${MGMT_IP_COUNT} ]]; then
        echo "WARN: Container ${WEKA_CONTAINER} has ${NET_COUNT} dataplane NICs, but ${MGMT_IP_COUNT} management IPs"
        RETURN_CODE=254

    # Ostensibly this should only occur in cloud environments?
    elif [[ ${SINGLE_IP} -eq 0 ]] && [[ ${MGMT_IP_COUNT} -gt 1 ]]; then
        echo "WARN: Container ${WEKA_CONTAINER} has ${MGMT_IP_COUNT} management IPs"
        RETURN_CODE=254
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All Weka dataplane NICs have valid management IPs"
else
    echo "Recommended Resolution: assign an appropriate set of management ips for each container."
    echo "There should be one management IP per dataplane NIC. Management IPs can be set"
    echo "by running the following command"
    echo " weka local resources --container <WEKA-CONTAINER> management-ips <IP1> <IP2>"
fi

exit ${RETURN_CODE}