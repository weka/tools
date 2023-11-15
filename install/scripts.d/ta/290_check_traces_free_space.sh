#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Verify that size of traces FS is larger than ensure-free"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

WEKA_TRACES_DIR="/opt/weka/traces"

WEKA_ENSURE_FREE=$(weka debug traces status --json | jq .servers_ensure_free.value)   # bytes
TRACES_FS_SIZE_KB=$(df -BK ${WEKA_TRACES_DIR} --output=size | tail -n -1 | sed s/K$//) # kibibytes
TRACES_FS_SIZE=$((${TRACES_FS_SIZE_KB}*1024)) # kibibytes


if (( ${WEKA_ENSURE_FREE} > ${TRACES_FS_SIZE})) ; then
    echo "Weka is currently set to ensure that ${WEKA_ENSURE_FREE} bytes are free"
    echo "on ${WEKA_TRACES_DIR}, but this filesystem is only ${TRACES_FS_SIZE} bytes" 
    echo "in size. These conditions cannot co-exist, so the outcome is that no"
    echo "traces will be stored"
    RETURN_CODE=1
fi 

exit ${RETURN_CODE}


