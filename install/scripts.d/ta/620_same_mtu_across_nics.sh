#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Compare MTUs across Weka containers"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-316504"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2024-09-18

# We send packets of either 1480 or 4056 bytes including UDP header, so including the IP header
# header that is either 1500 or 4076 bytes.
SMALLEST_MTU_REQUIRED=1500
for CONTAINER in $(weka local ps --no-header | awk '{print $1}' | grep -vw -e envoy -e ganesha -e samba -e smbw -e s3 -e dataserv) ; do
    for PCI_ID in $(weka local resources net --container ${CONTAINER} --stable | grep -v ^NET | awk '{print $2}') ; do
        MTU=$(cat /sys/bus/pci/devices/${PCI_ID}/net/*/mtu 2>/dev/null)
        # If one MTU is large... They all should be
        if [[ -n ${MTU} && ${MTU} -ge 4076 ]] ; then
            SMALLEST_MTU_REQUIRED=4076
        fi
    done
done


for CONTAINER in $(weka local ps --no-header | awk '{print $1}' | grep -vw -e envoy -e ganesha -e samba -e smbw -e s3 -e dataserv) ; do
    for PCI_ID in $(weka local resources net --container ${CONTAINER} --stable | grep -v ^NET | awk '{print $2}') ; do
        MTU=$(cat /sys/bus/pci/devices/${PCI_ID}/net/*/mtu 2>/dev/null)
        if [[ -n ${MTU} && ${MTU} -lt ${SMALLEST_MTU_REQUIRED} ]] ; then
            echo "The NIC identified by the PCI ID ${PCI_ID} used by container ${CONTAINER}"
            echo "has an MTU of ${MTU}, which is less than the MTU ${SMALLEST_MTU_REQUIRED} seen elsewhere in this host"
            echo "This can lead to cluster communication problems"
            echo "Please see ${JIRA_REFERENCE} for more information"
            echo "Recommended Resolution: Increase the MTUs of all NICs in the cluster to at least ${SMALLEST_MTU_REQUIRED}"
            echo "Review your OS documentation for how to set this permanently, but NetworkManager-based OSes will use"
            echo "something like \"nmcli connection modify eno1 802-3-ethernet.mtu ${SMALLEST_MTU_REQUIRED}\" and then"
            echo "\"nmcli connection apply eno1\", but connection names will vary"
            RETURN_CODE=254
        fi
    done
done

if [[ ${RETURN_CODE} -eq 0 ]] ; then
   echo "No mismatched large/small MTUs found"
fi

exit $RETURN_CODE
