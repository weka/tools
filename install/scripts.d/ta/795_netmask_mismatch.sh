#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if netmask configured in container resources matches netmask on interface"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
RC=$?

case ${RC} in
    254)
        echo "ERROR: Not able to run weka commands."
        exit 254
        ;;
    127)
        echo "WEKA not found."
        exit 254
        ;;
    41)
        echo "Unable to login to Weka cluster."
        exit 254
        ;;
esac

while read WEKA_CONTAINER WEKA_CONTAINER_PORT; do
    NET_IP=""
    NET_NAME=""
    NET_MASK=""
    SINGLE_IP=""

    while read PORTS; do
        if [[ $PORTS =~ ip:([^n]+)netdevName:([^n]+)netmaskBits:([^s]+)singleIP:([^ ]+) ]]; then
        #if [[ ${PORTS} =~ "ip:"(.*)"netdevName:"(.*)"netmaskBits:"(.*)"singleIP:"(.*) ]]; then
            NET_IP=${BASH_REMATCH[1]}
            NET_NAME=${BASH_REMATCH[2]}
            NET_MASK=${BASH_REMATCH[3]}
            SINGLE_IP=${BASH_REMATCH[4]}
        fi

        if [[ -z ${NET_IP} || -z ${NET_NAME} || -z ${NET_MASK} || -z ${SINGLE_IP} ]]; then
            echo "ERROR: Parsing error."
            exit 255;

        elif [[ ${SINGLE_IP} == "true" ]]; then
            NET_OS=$(ip -j -o addr show dev ${NET_NAME} 2>/dev/null)
            if [[ $? -eq 0 ]]; then
                if [[ $(echo "${NET_OS}" | tr -d \"\[:blank:]) =~ "${NET_IP},prefixlen:"([0-9]+) ]]; then
                    NET_MASK_OS=${BASH_REMATCH[1]}
                    if [[ ${NET_MASK} != ${NET_MASK_OS} ]]; then
                        echo "WARN: ${NET_NAME} has netmask mismatch between weka resources (${NET_MASK}) and OS (${NET_MASK_OS}):"
                        echo "Recommended Resolution: determine the correct netmasks of the interfaces being used by Weka."
                        echo "If Weka needs to be reconfigured, this will be done with commands like:"
                        echo " weka local resources -C <WEKA-CONTAINER> net remove <NIC>"
                        echo " weka local resources -C <WEKA-CONTAINER> net add    <NIC> --netmask <BIT-LENGTH> --gateway <OPTIONAL GATEWAY>"
                        echo " weka local resources -C <WEKA-CONTAINER> apply"
                        RETURN_CODE=254
                    fi
                fi
            else
                echo "ERROR: Specified NIC (${NET_NAME}) not found."
                echo "Recommended Resolution: ensure the resource configuration is properly specified."
                echo "Review the output of weka local resources -C ${WEKA_CONTAINER} for validity."
                RETURN_CODE=255
            fi
        fi
    done < <(weka debug manhole -s 1 network_get_dpdk_ports -P ${WEKA_CONTAINER_PORT}  | grep -e "ip" -e "netdevName" -e "netmaskBits" -e "singleIP" | paste - - - - | tr -d \"\,[:blank:])
done < <(weka local ps --output name,port --no-header | awk '/compute|drive|frontend/')

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All Weka containers have consistent netmasks"
fi

exit ${RETURN_CODE}
