#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for more than supported number of NUMA domains"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-361715"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

main () {
    MAXIMUM_NUMA_DOMAINS="20" # as of 4.2.11

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
    NUMBER_OF_NUMA_DOMAINS=$(ls -d /sys/devices/system/node/node* |wc -l)
    echo "Detected $NUMBER_OF_NUMA_DOMAINS NUMA domains."

    # More than 20 NUMAs is unsupported
    if [[ $NUMBER_OF_NUMA_DOMAINS -gt $MAXIMUM_NUMA_DOMAINS ]]; then
        RETURN_CODE=254
        echo "Weka currenty only supports a maximum of 20 NUMA domains (4.2.11+)."

    # 8 or fewer NUMAs is always supported
    elif [[ $NUMBER_OF_NUMA_DOMAINS -le 8 ]]; then
        echo "Number of NUMA domains is within supported limits."

    # 16 or higher NUMAs only supported in 4.2.11+
    elif vergt $WEKA_VERSION "4.2.6" && verlt $WEKA_VERSION "4.2.11" && [[ $NUMBER_OF_NUMA_DOMAINS -gt 16 ]]; then
        RETURN_CODE=254
        echo "Weka only supports more than 16 NUMA domains in 4.2.11 and higher."

    # 8 or higher NUMAs only supported in 4.2.7+
    elif verlt $WEKA_VERSION "4.2.7" && [[ $NUMBER_OF_NUMA_DOMAINS -gt 8 ]]; then
        RETURN_CODE=254
        echo "Weka only supports more than 8 NUMA domains in 4.2.7 and higher."

    else
        echo "Number of NUMA domains is within supported limits."
    fi

    exit ${RETURN_CODE}
}

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


main "$@"; exit
