#!/bin/bash

DESCRIPTION="Check for IOMMU status"
SCRIPT_TYPE="parallel"


#find /sys | grep dmar &> /dev/null
#if [ $? == 0 ]; then    # found a dmar, which we don't want
#    echo "ERROR: IOMMU is enabled on `hostname`"
#    exit "1"
#else
#    echo "IOMMU disabled"
#fi

iommuclass=`ls /sys/class/iommu | wc -l`
iommugroups=`ls /sys/kernel/iommu_groups | wc -l`
if [ $iommuclass -eq "0" ] && [ $iommugroups -eq "0" ]; then    # check for iommu devices
    echo "IOMMU not configured on `hostname`"
    ret="0"
else
    echo "IOMMU configured on `hostname` "
    ret="0"
fi

exit $ret


