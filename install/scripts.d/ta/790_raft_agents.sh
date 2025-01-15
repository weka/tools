#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Examine the number of Raft agents used vs maximum"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
RETURN_CODE=0
WEKA_VERSION=$(weka version current)

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

# we can't rely on jq being present
WEKA_BUCKET_COUNT=$(weka status | grep Buckets | sed 's/.*[^0-9]\([0-9][0-9]*\) Buckets.*/\1/')
WEKA_COMPUTE_PROCESS_COUNT=$(weka cluster process -b -F role=COMPUTE --no-header --output id | wc -l)
WEKA_RAFT_AGENTS=$((${WEKA_BUCKET_COUNT}*5))
WEKA_MAX_RAFT_AGENTS=$((${WEKA_COMPUTE_PROCESS_COUNT}*180))

if [[ ${WEKA_RAFT_AGENTS} -gt ${WEKA_MAX_RAFT_AGENTS} ]] ; then 
    echo "The maximum number of raft agents recommended per compute node is 180. This cluster requires ${WEKA_RAFT_AGENTS} in total"
    echo "Recommended resolution: scale out your cluster by adding more compute processes or perhaps backend WEKA servers"
    RETURN_CODE=254
fi
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Fewer than the recommended maximum number of raft agents per compute node in use"
fi
exit ${RETURN_CODE}
