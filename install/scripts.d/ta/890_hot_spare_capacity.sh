#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check we have sufficient capacity in case of failure"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
REFERENCE=""

RETURN_CODE=0


HOT_SPARE=$(weka status -J | grep -w hot_spare | sed 's/[^0-9]//g')

if [[ ${HOT_SPARE} -ge 1 ]] ; then
    echo "We have at least one hot spare configured, no further checking required"
    exit 0
fi


# We have 0 hot-spares, which is likely at least bad
RETURN_CODE=254

NUM_DATA_DISKS=$(weka status -J | grep -w stripe_data_drives | sed 's/[^0-9]//g')
# What happens if we lose 1 FD?
THRESHOLD_FILL_LEVEL=$(awk -v data_disks=${NUM_DATA_DISKS} 'BEGIN { printf "%d", ((data_disks-1) / data_disks) * 100 }')

for WEKAFS in $(weka fs -o name --no-header) ; do
    USED_SSD=$(     weka fs -F name=${WEKAFS} -J | grep -w used_ssd      | sed 's/[^0-9]//g')
    AVAILABLE_SSD=$(weka fs -F name=${WEKAFS} -J | grep -w available_ssd | sed 's/[^0-9]//g')
    RATIO=$(awk -v used=${USED_SSD} -v available=${AVAILABLE_SSD} 'BEGIN { printf "%d", (used / available) * 100}')
    if [[ ${RATIO} -ge ${THRESHOLD_FILL_LEVEL} ]] ; then
        echo "Filesystem ${WEKAFS} is ${RATIO}% full, and may suffer write hanging in the loss of a failure domain"
        echo "Recommended resolution: allocate a hot-spare"
        RETURN_CODE=254
    fi
done
    
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No problems detected"
else
    echo "At least one filesystem has been identified which is filled beyond the capacity "
    echo " calculated to be available if a single failure domain were to be lost."
    echo "This might lead to write hangs in the case of hardware failure."
    echo "Recommended resolution: Allocate hot-spare capacity or otherwise increase free space"
fi


exit ${RETURN_CODE}
