#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for network mode consistency"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

declare -A NETWORK_MODES

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


# Iterate over backend weka containers (compute and drives)
for ROLE in COMPUTE DRIVES; do
    if [[ $(weka cluster process -F role=${ROLE} -o netmode --no-header | sort | uniq | wc -l) -gt 1 ]]; then
        RETURN_CODE=254
        echo "WARNING: $ROLE process network modes are inconsistent"
        echo "Recommended Resolution: contact Customer Success to ensure that each container is defined correctly"
    fi
done


if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Backend process network modes are consistent."
fi

exit $RETURN_CODE
