#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for NFS floating IPs on v4 services"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
JIRA_REFERENCE="WEKAPP-298483"
WTA_REFERENCE=""
KB_REFERENCE="KB 1184"

RETURN_CODE=0

WEKA_NFS_V4_SUPPORT_IN_USE=$(weka nfs permission --json  | jq ".[].supported_versions" | grep V4 | wc -l)
WEKA_NFS_INTERFACE_GROUP_WITH_FLOATING_IPS_COUNT=$(weka nfs interface-group --json | jq '.[].ips | length' | grep -v "^0$" | wc -l)

if [[ ( ${WEKA_NFS_V4_SUPPORT_IN_USE} -ne "0" ) && \
      ( ${WEKA_NFS_INTERFACE_GROUP_WITH_FLOATING_IPS_COUNT} -ne "0" ) ]] ; then
    RETURN_CODE=1
    echo "There are NFS v4 services in use with floating IPs - potentially susceptible"
    if [[ ! -z "${WTA_REFERENCE}" ]]; then
        echo "to ${JIRA_REFERENCE}, discussed in ${WTA_REFERENCE}, SFDC ${KB_REFERENCE}"
    else
        echo "to ${JIRA_REFERENCE}, SFDC ${KB_REFERENCE}"                                                                                                   
    fi
    echo "This does not necessarily prove a problem, and should be investigated"
fi

exit ${RETURN_CODE}
