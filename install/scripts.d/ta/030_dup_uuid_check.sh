#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for duplicate UUIDs"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="KB-000001227"

RETURN_CODE=0

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

if [[ $(weka cluster container --no-header -o machineIdentifier,hostname | sort -u | awk '{print $1}' | uniq -d) ]]; then
    echo "WARN: Duplicate UUIDs detected"
    RETURN_CODE=254
else
    echo "No duplicate UUIDs detected"
fi

exit $RETURN_CODE
