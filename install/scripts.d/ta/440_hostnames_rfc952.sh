#!/bin/bash

#set -ue # Fail with an error code if there is any sub-command/variable error

DESCRIPTION="Ensure valid hostnames according to RFC 952"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

SHORT_HOSTNAME=$(hostname -s)

LENGTH_HOSTNAME=$(echo -n ${SHORT_HOSTNAME} | wc -c)

if [[ ${LENGTH_HOSTNAME} -eq "1" ]] ; then
    echo "Single-character hostnames are not permitted"
    RETURN_CODE=254
    exit ${RETURN_CODE}
fi

# Use an inverted regex class to search for invalid characters - thus if grep finds a match it's invalid
GREP_RESULT=$(echo ${SHORT_HOSTNAME} | grep "[^-a-z0-9.]")
if [[ $? -eq 0 ]]; then
    echo "The hostname ${SHORT_HOSTNAME} appears to contain a character other than [a-z], -, and [0-9]."
    echo "Refer to RFC 952 for more information"
    echo "Recommended resolution: change the hostname to include only alphanumerics and underscores"
    RETURN_CODE=254
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "The hostname ${SHORT_HOSTNAME} appears to be valid according to RFC 952"
fi
exit ${RETURN_CODE}
