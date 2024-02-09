#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for existence of /data folder"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-329531"
WTA_REFERENCE=""
KB_REFERENCE="KB 1179"
RETURN_CODE=0
MIN_VERSION="4.1.2"
MAX_VERSION="4.2.3"

# Use core-util's sort -V to dermine if version $1 is <= version $2
verlte() {
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}
verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

WEKA_VERSION=$(weka version current)

if [ -d "/data" ] ; then 
    if verlte ${MIN_VERSION} ${WEKA_VERSION} && verlte ${WEKA_VERSION} ${MAX_VERSION} ; then
        echo "The folder /data exists, and this version of Weka is susceptible"
        if [[ ! -z "${WTA_REFERENCE}" ]]; then
            echo "to ${JIRA_REFERENCE}, discussed in ${WTA_REFERENCE}, SFDC ${KB_REFERENCE}"
        else
            echo "to ${JIRA_REFERENCE}, SFDC ${KB_REFERENCE}"                                                                                                   
        fi
        RETURN_CODE=1
    fi
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No /data folder exists"
fi
exit ${RETURN_CODE}
