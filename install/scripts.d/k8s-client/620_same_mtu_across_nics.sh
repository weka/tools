#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Compare MTUs across high-speed NICs"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-316504"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2026-09-10
# k8s-client variant: does not use the weka CLI. Without container resources to
# tell us which NICs are dataplane, treat every connected ethernet/Infiniband
# port at or above DATAPLANE_MIN_SPEED Mb/s as a dataplane candidate.

DATAPLANE_MIN_SPEED=25000

# We send packets of either 1480 or 4056 bytes including UDP header, so including the IP header
# header that is either 1500 or 4076 bytes.
SMALLEST_MTU_REQUIRED=1500
declare -A NIC_MTUS

for DEVICE_PATH in /sys/class/net/* ; do
    DEVICE=${DEVICE_PATH##*/}
    TYPE=$(cat ${DEVICE_PATH}/type 2>/dev/null)
    if [[ "${TYPE}" != "1" && "${TYPE}" != "32" ]] ; then
        continue
    fi
    if [[ "$(cat ${DEVICE_PATH}/carrier 2>/dev/null)" != "1" ]] ; then
        continue
    fi
    SPEED=$(cat ${DEVICE_PATH}/speed 2>/dev/null)
    if [[ -z ${SPEED} || ${SPEED} -lt ${DATAPLANE_MIN_SPEED} ]] ; then
        continue
    fi
    MTU=$(cat ${DEVICE_PATH}/mtu 2>/dev/null)
    if [[ -z ${MTU} ]] ; then
        continue
    fi
    NIC_MTUS[${DEVICE}]=${MTU}
    # If one MTU is large... They all should be
    if [[ ${MTU} -ge 4076 ]] ; then
        SMALLEST_MTU_REQUIRED=4076
    fi
done

if [[ ${#NIC_MTUS[@]} -eq 0 ]] ; then
    echo "No connected NICs at or above ${DATAPLANE_MIN_SPEED} Mb/s found, nothing to compare"
    exit 0
fi

for DEVICE in "${!NIC_MTUS[@]}" ; do
    MTU=${NIC_MTUS[${DEVICE}]}
    if [[ ${MTU} -lt ${SMALLEST_MTU_REQUIRED} ]] ; then
        echo "The NIC ${DEVICE} has an MTU of ${MTU}, which is less than the MTU ${SMALLEST_MTU_REQUIRED} seen on another"
        echo "high-speed NIC in this host. This can lead to cluster communication problems"
        echo "Please see ${JIRA_REFERENCE} for more information"
        echo "Recommended Resolution: Increase the MTUs of all dataplane NICs to at least ${SMALLEST_MTU_REQUIRED}"
        echo "Review your OS documentation for how to set this permanently, but NetworkManager-based OSes will use"
        echo "something like \"nmcli connection modify eno1 802-3-ethernet.mtu ${SMALLEST_MTU_REQUIRED}\" and then"
        echo "\"nmcli connection apply eno1\", but connection names will vary"
        RETURN_CODE=254
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]] ; then
   echo "No mismatched large/small MTUs found across ${#NIC_MTUS[@]} high-speed NIC(s)"
fi

exit $RETURN_CODE
