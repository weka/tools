#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check Weka DPDK network devices have IP gateways"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header | grep -vw -e envoy -e ganesha -e samba -e smbw -e s3); do
    DEVICES_WITH_NO_GATEWAY=""
    NET_DEVICE=""
    NET_GATEWAY=""

    while read NET_ENTRY; do
        if [[ ${NET_ENTRY} =~ "gateway:"(.*)"name:"(.*) ]]; then
            NET_GATEWAY=${BASH_REMATCH[1]}
            NET_DEVICE=${BASH_REMATCH[2]}
        fi

        if [[ -n ${NET_DEVICE} ]]; then
            if [[ -d /sys/class/net/${NET_DEVICE} ]]; then
                NET_TYPE=$(cat /sys/class/net/${NET_DEVICE}/type)
                if [[ -n ${NET_TYPE} && ${NET_TYPE} == "1" ]]; then # Only check ethernet devices
                    if [[ -z ${NET_GATEWAY} ]]; then
                        DEVICES_WITH_NO_GATEWAY="${DEVICES_WITH_NO_GATEWAY}${NET_DEVICE} "
                    fi
                fi
            fi
        fi
    done < <(weka local resources -C ${WEKA_CONTAINER} net --stable -J | grep -w -e gateway -e name | paste - - | tr -d \"\,[:blank:])

    if [[ -n ${DEVICES_WITH_NO_GATEWAY} ]]; then
        echo "The container ${WEKA_CONTAINER} has the network device(s) ${DEVICES_WITH_NO_GATEWAY}"
        echo "defined without an IP gateway - this might not be a mistake but means Weka"
        echo "POSIX traffic will not leave this subnet."
        echo "The likely fix for this is to do weka local resources net remove for each device,"
        echo "then add back in with weka local resource net add <DEVNAME> --gateway ... --netmask .."
        echo
        RETURN_CODE=254
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All Weka containers have network devices with gateways"
fi

exit ${RETURN_CODE}