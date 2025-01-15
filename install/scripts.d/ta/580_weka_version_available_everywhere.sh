#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if Weka agent version matches cluster version"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-364875"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

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

WEKA_CLUSTER_VERSION=$(weka status | awk 'NR==1{print $2}' | tr -d 'v')
CURRENT_AGENT_VERSION=$(weka local status | awk 'NR==1{print $5}' | tr -d ')')
if [[ ${WEKA_CLUSTER_VERSION} != ${CURRENT_AGENT_VERSION} ]] ; then
    echo "The currently running cluster version ${WEKA_CLUSTER_VERSION} does not match the"
    echo "default installed local agent version ${CURRENT_AGENT_VERSION}"
    echo "Recommended Resolution: update this host to the cluster version, either by"
    echo " unmounting and re-mounting filesystems or using the weka local upgrade utility"
    RETURN_CODE="254"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Weka local agent matches cluster running version"
fi

exit ${RETURN_CODE}
