#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for drives beyond version-specific supported capacities"
SCRIPT_TYPE="single"
JIRA_REFERENCE="WEKAPP-324010"
WTA_REFERENCE=""
KB_REFERENCE="KB1172"
RETURN_CODE=0

LARGEST_SUPPORTED_SSD="29000000000000" # no version specific info beyond "before 4.1.2"

# Derived from https://stackoverflow.com/questions/4023830/how-to-compare-two-strings-in-dot-separated-version-format-in-bash
verlte() {
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}       

verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

vergt() {
    [ "$1" = "$2" ] && return 1 || verlte $2 $1
}

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

WEKA_VERSION=$(weka version | grep -E ^\* | cut -d ' ' -f2)
LARGEST_SSD=$(weka cluster drive --output size --sort size --raw-units --no-header | tail -n 1 | sed "s/[^0-9]*//g")
if verlt ${WEKA_VERSION} "4.1.2" && [[ ${LARGEST_SSD} -gt ${LARGEST_SUPPORTED_SSD} ]]; then
    RETURN_CODE=254
    echo "Weka only supports SSDs larger than ${LARGEST_SUPPORTED_SSD} in versions after 4.1.2"
    echo "Refer to ${KB_REFERENCE} or ${JIRA_REFERENCE} for more information"

else
    echo "No SSDs are beyond supported capacities"
fi

exit ${RETURN_CODE}


