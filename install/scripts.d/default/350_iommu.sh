#!/bin/bash

DESCRIPTION="Check that IOMMU is set the same on all"
# just make sure all the servers are the same
SCRIPT_TYPE="parallel-compare-backends"



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
    echo "IOMMU is not configured"
else
    echo "IOMMU is configured"
fi

exit "0"


