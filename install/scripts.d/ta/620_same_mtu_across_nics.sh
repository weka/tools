#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Compare MTUs across Weka containers"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-316504"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2024-04-30

main() {
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

    # We send packets of either 1480 or 4056 bytes including UDP header, so including the IP header
    # header that is either 1500 or 4076 bytes.
    SMALLEST_MTU_REQUIRED=1500
    for CONTAINER in $(weka local ps --no-header | awk '{print $1}' | grep -vw -e ganesha -e smbw -e s3) ; do
        for PCI_ID in $(weka local resources net --container ${CONTAINER} --stable | grep -v ^NET | awk '{print $2}') ; do
            MTU=$(cat /sys/bus/pci/devices/${PCI_ID}/net/*/mtu)
            # If one MTU is large... They all should be
            if [[ ${MTU} -ge 4076 ]] ; then
                SMALLEST_MTU_REQUIRED=4076
            fi
        done
    done
    
    for CONTAINER in $(weka local ps --no-header | awk '{print $1}' | grep -vw -e ganesha -e smbw -e s3) ; do
        for PCI_ID in $(weka local resources net --container ${CONTAINER} --stable | grep -v ^NET | awk '{print $2}') ; do
            MTU=$(cat /sys/bus/pci/devices/${PCI_ID}/net/*/mtu)
            if [[ ${MTU} -lt ${SMALLEST_MTU_REQUIRED} ]] ; then
                    echo "The NIC identified by the PCI ID ${PCI_ID} used by container ${CONTAINER}"
                    echo "has an MTU of ${MTU}, which is less than the MTU ${SMALLEST_MTU_REQUIRED} seen elsewhere in this host"
                    echo "This can lead to cluster communication problems"
                    echo "Please see ${JIRA_REFERENCE} for more information"
                    RETURN_CODE=254
            fi
        done
    done
    
    if [[ ${RETURN_CODE} -eq 0 ]] ; then
        echo "No mismatched large/small MTUs found"
    fi
    
    exit $RETURN_CODE
}

main "$@"
