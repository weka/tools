#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if netmask configured in container resources matches netmask on interface"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header | grep -vw -e envoy -e ganesha -e samba -e smbw -e s3); do
    NET_NAME=""
    NET_MASK=""

    while read NET_ENTRY; do
        if [[ ${NET_ENTRY} =~ "name:"(.*)"netmask:"(.*) ]]; then
            NET_NAME=${BASH_REMATCH[1]}
            NET_MASK=${BASH_REMATCH[2]}
        fi

        if [[ -n ${NET_NAME} ]]; then
            if [[ $(ip -4 -j -o addr show dev ${NET_NAME} 2>/dev/null | tr -d \"\[:blank:]) =~ "prefixlen:"([0-9]+)"," ]]; then
                NET_OS=${BASH_REMATCH[1]}
                if [[ ${NET_MASK} != ${NET_OS} ]]; then
                    echo "WARN: ${NET_NAME} has netmask mismatch between weka resources and OS: ${NET_MASK} != ${NET_OS}"
                    RETURN_CODE=254
                fi
            fi
        fi
    done < <(weka local resources -C ${WEKA_CONTAINER} net --stable -J | grep -w -e netmask -e name | paste - - | tr -d \"\,[:blank:])
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All Weka containers have consistent netmasks"
else 
    echo "Recommended Resolution: determine which of these netmasks is correct, and rectify the one with"
    echo "the wrong configuration. If Weka needs re-configuring, this will be done with commands like"
    echo " weka local resources --container <WEKA-CONTAINER> net remove <NIC>"
    echo " weka local resources --container <WEKA-CONTAINER> net add    <NIC> --netmask <BIT-LENGTH>"
fi

exit ${RETURN_CODE}
