#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Verify that size of traces FS is larger than ensure-free"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

WEKA_TRACES_DIR="/opt/weka/traces"

# check if we can run weka commands
weka status &> /dev/null
status=$?
if [[ $status -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    if [[ $status -eq 127 ]]; then
        echo "WEKA not found"
    elif [[ $status -eq 41 ]]; then
        echo "Unable to log into Weka cluster"
    fi
    exit 254 # WARN
fi

WEKA_ENSURE_FREE=$(weka debug traces status --json | python3 -c '
from __future__ import print_function
import sys, json
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print("ERROR: Unable to decode JSON from weka debug traces status")
    print(e)
    sys.exit(1)
try:
    print(data["servers_ensure_free"]["value"])
except KeyError as e:
    print("ERROR: Unable to find servers_ensure_free in JSON from weka debug traces status")
    print(e)
    sys.exit(1)
')   # bytes
# check if the python script failed (WEKA_ENSURE_FREE is not a number)
if ! [[ $WEKA_ENSURE_FREE =~ ^[0-9]+$ ]]; then
    echo ${WEKA_ENSURE_FREE}
    exit 1
fi
TRACES_FS_SIZE_KB=$(df -BK ${WEKA_TRACES_DIR} --output=size | tail -n -1 | sed s/K$//) # kibibytes
TRACES_FS_SIZE=$((${TRACES_FS_SIZE_KB}*1024)) # kibibytes


if (( ${WEKA_ENSURE_FREE} > ${TRACES_FS_SIZE})) ; then
    echo "Weka is currently set to ensure that ${WEKA_ENSURE_FREE} bytes are free"
    echo "on ${WEKA_TRACES_DIR}, but this filesystem is only ${TRACES_FS_SIZE} bytes" 
    echo "in size. These conditions cannot co-exist, so the outcome is that no"
    echo "traces will be stored."
    echo "Recommended options:"
    echo "   . Increase the size of ${WEKA_TRACES_DIR}"
    echo "   . Reduce the size of traces with \"weka debug traces retention set --server-ensure-free XXXX\""
    RETURN_CODE=1
fi 
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Traces FS is larger than ensure-free"
fi
exit ${RETURN_CODE}


