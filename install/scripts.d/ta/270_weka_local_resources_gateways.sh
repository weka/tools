#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check Weka DPDK network devices have IP gateways"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header); do
    if [[ ( ${WEKA_CONTAINER} == "ganesha" ) || \
          ( ${WEKA_CONTAINER} == "samba" )   || \
          ( ${WEKA_CONTAINER} == "smb"   ) ]] ; then
        continue
    fi
    # Look for network devices with no gateway
    RESOURCES=$(sudo weka local resources --container ${WEKA_CONTAINER} --json)
    NUMBER_OF_DEVICES_WITH_NO_GATEWAY=$(echo ${RESOURCES} | python3 -c 'import sys, json; data = json.load(sys.stdin); print(len([device for device in data["net_devices"] if device["gateway"] == ""]))')


    if [[ ${NUMBER_OF_DEVICES_WITH_NO_GATEWAY} -ne 0 ]] ; then
        DEVICES_WITH_NO_GATEWAY=$(echo ${RESOURCES} | python3 -c 'import sys, json; data = json.load(sys.stdin); print("\n".join([device["name"] for device in data["net_devices"] if device["gateway"] == ""]))')
        echo "The container ${WEKA_CONTAINER} has the following network devices defined without an IP"
        echo "gateway - this might not be a mistake but means Weka POSIX traffic will not"
        echo "leave this subnet"
        echo ""
        echo ${DEVICES_WITH_NO_GATEWAY}
        echo ""
        echo "The likely fix for this is to do weka local resources net remove for each device,"
        echo "then add back in with weka local resource net add <DEVNAME> --gateway ... --netmask .."
        #RETURN_CODE=254
        exit 254
    fi 
done
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All Weka containers have network devices with gateways"
fi
exit ${RETURN_CODE}


