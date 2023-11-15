#!/bin/bash

DESCRIPTION="Check for IOMMU disabled"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-323895"
WTA_REFERENCE=""
RETURN_CODE=0
MIN_VERSION="4.1.2"
MAX_VERSION="4.2.2"

# Use core-util's sort -V to dermine if version $1 is <= version $2
verlte() {
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}
verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

WEKA_VERSION=$(weka version current)

IOMMUCLASS=$(ls /sys/class/iommu | wc -l)
IOMMUGROUPS=$(ls /sys/kernel/iommu_groups | wc -l)

if [ $IOMMUCLASS -eq "0" ] && [ $IOMMUGROUPS -eq "0" ]; then    # check for iommu devices
    echo "IOMMU not configured on $(hostname)"
    ret="0"
else
    if verlte ${MIN_VERSION} ${WEKA_VERSION} && verlte ${WEKA_VERSION} ${MAX_VERSION} ; then
        echo "This version is classified as a susceptible version, and"
    fi
    echo "IOMMU is configured on $(hostname) - this should be disabled - refer"
    if [[ ! -z "${WTA_REFERENCE}" ]]; then
        echo "to ${JIRA_REFERENCE}, discussed in ${WTA_REFERENCE}"
    else
        echo "to ${JIRA_REFERENCE}"                                                                                                   
    fi
    RETURN_CODE=1
fi

exit ${RETURN_CODE}
