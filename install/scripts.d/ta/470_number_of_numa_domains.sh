#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for more than supported number of NUMA domains"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-361715"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Derived from https://stackoverflow.com/questions/4023830/how-to-compare-two-strings-in-dot-separated-version-format-in-bash
vergte() {
    [  "$1" = "$(echo -e "$1\n$1" | sort -V | tail -n1)" ]
}

verlte() {
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}

verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

vergt() {
    [ "$1" = "$2" ] && return 1 || verlte $2 $1
}

MAXIMUM_NUMA_DOMAINS="32" # as of 4.2.11 (WEKAPP-381838)

WEKA_VERSION=$(weka version | grep -e "^\*" | tr -d '*')
NUMBER_OF_NUMA_DOMAINS=$(ls -d /sys/devices/system/node/node* |wc -l)
echo -n "Detected $NUMBER_OF_NUMA_DOMAINS NUMA domains - "

# More than 32 NUMAs is unsupported
if [[ $NUMBER_OF_NUMA_DOMAINS -gt $MAXIMUM_NUMA_DOMAINS ]]; then
    RETURN_CODE=254
    echo "Weka currenty only supports a maximum of 32 NUMA domains (4.2.11+)."

# 8 or fewer NUMAs is always supported
elif [[ $NUMBER_OF_NUMA_DOMAINS -le 8 ]]; then
    echo "Number of NUMA domains is within supported limits."

# More than 16 NUMAs only supported in 4.3.2+
elif vergte $WEKA_VERSION "4.3.0" && verlt $WEKA_VERSION "4.3.2" && [[ $NUMBER_OF_NUMA_DOMAINS -gt 16 ]]; then
    RETURN_CODE=254
    echo "Weka only supports more than 16 NUMA domains in 4.3.2 and higher."

# More than 16 NUMAs only supported in 4.2.11+
elif vergt $WEKA_VERSION "4.2.6" && verlt $WEKA_VERSION "4.2.11" && [[ $NUMBER_OF_NUMA_DOMAINS -gt 16 ]]; then
    RETURN_CODE=254
    echo "Weka only supports more than 16 NUMA domains in (4.2.11+, 4.3.2+)."

# More than 8 NUMAs only supported in 4.2.7+
elif verlt $WEKA_VERSION "4.2.7" && [[ $NUMBER_OF_NUMA_DOMAINS -gt 8 ]]; then
    RETURN_CODE=254
    echo "Weka only supports more than 8 NUMA domains in 4.2.7 and higher."
else
    echo "Number of NUMA domains is within supported limits."
fi

exit ${RETURN_CODE}
