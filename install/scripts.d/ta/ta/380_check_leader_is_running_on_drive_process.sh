#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check cluster leader is running on a DRIVES process"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""

RETURN_CODE=0

# Need to check the container rather than the process, as it'll only ever be part of a MANAGEMENT process,
# so easiest to check the container/host has the DRIVES role
WEKA_CLUSTER_LEADER_CONTAINER=$(weka cluster host --leader --no-header --output id 2>/dev/null)
WEKA_NUMBER_OF_DRIVE_PROCESSES=$(weka cluster host resources --json ${WEKA_CLUSTER_LEADER_CONTAINER} | jq -cr '.nodes[].roles|select(.[0]=="DRIVES")|length' 2>/dev/null)

if [[ ( ${WEKA_NUMBER_OF_DRIVE_PROCESSES} -eq "0" ) ]] ; then 
    RETURN_CODE=1
    echo "The weka cluster leader is running in container ${WEKA_CLUSTER_LEADER_CONTAINER},"
    echo "which does not appear to contain any processes running the DRIVES role"
    echo "This does not necessarily prove a problem, and should be investigated"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "The weka cluster leader is running on a DRIVES process"
fi
exit ${RETURN_CODE}
