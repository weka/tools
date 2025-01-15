#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Examine the amount of SSD space used vs maximum"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
RETURN_CODE=0
WEKA_VERSION=$(weka version current)

# we can't rely on jq being present
WEKA_BUCKET_COUNT=$(weka status | grep Buckets | sed 's/.*[^0-9]\([0-9][0-9]*\) Buckets.*/\1/')
WEKA_SSD_USED_BYTES=$(weka fs -o usedSSD --no-header -R | awk '{tot+=$1}; END {print tot}')

# gets a syntax error if this isn't numeric... so check
if [[ ${WEKA_SSD_USED_BYTES} =~ ^-?[0-9]+$ ]]; then
    echo "Used bytes is ${WEKA_SSD_USED_BYTES}"
else
    echo ${WEKA_SSD_USED_BYTES}
    exit 0
fi

# Theoretical max is 8 TiB per bucket
WEKA_THEORETICAL_MAX_SSD_BYTES=$((${WEKA_BUCKET_COUNT}*8*1024**4))
echo ${WEKA_SSD_USED_BYTES}

# if we've allocated more than half the maximum theoretical SSD space, warn
if [[ $((${WEKA_SSD_USED_BYTES}*2)) -gt ${WEKA_THEORETICAL_MAX_SSD_BYTES} ]] ; then 
    echo "You have used a significant proportion of the theoretical maximum"
    echo "NVME capacity of the cluster which is decided at first install time."
    echo "Please contact customer success to discuss options. Possible actions include:"
    echo " . Adding an Object Store to expand data storage while keeping NVME capacity down"
    echo " . In-place cluster resizing and migration (perhaps via snap2obj for fast backup/restore)"
    echo " . Migrating to a different, larger cluster"
    echo " . Pruning unnecessary data"
    RETURN_CODE=254
fi
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "SSD space used is less than half the theoretical maximum"
fi
exit ${RETURN_CODE}
