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
# Theoretical max is 8 TiB per bucket
WEKA_THEORETICAL_MAX_SSD_BYTES=$((${WEKA_BUCKET_COUNT}*8*1024**4))

# if we've allocated more than half the maximum theoretical SSD space, warn
if [[ $((${WEKA_SSD_USED_BYTES}*2)) -gt ${WEKA_THEORETICAL_MAX_SSD_BYTES} ]] ; then 
    RETURN_CODE=254
fi
exit ${RETURN_CODE}
