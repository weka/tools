#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for NFS floating IPs on v4 services"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
JIRA_REFERENCE="WEKAPP-298483"
WTA_REFERENCE=""
KB_REFERENCE="KB 1184"

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
WEKA_NFS_V4_SUPPORT_IN_USE=$(weka nfs permission --json  | python3 -c '
from __future__ import print_function
import sys, json
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print("ERROR: Unable to decode JSON from weka nfs permission")
    print(e)
    sys.exit(1)
print(len([permission for permission in data if "V4" in permission.get("supported_versions", [])]))
')
if ! [[ $WEKA_NFS_V4_SUPPORT_IN_USE =~ ^[0-9]+$ ]]; then
    echo ${WEKA_NFS_V4_SUPPORT_IN_USE}
    exit 1
fi
WEKA_NFS_INTERFACE_GROUP_WITH_FLOATING_IPS_COUNT=$(weka nfs interface-group --json | python3 -c 'import sys, json; data = json.load(sys.stdin); print(sum([len(ig["ips"]) for ig in data]))')

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
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No NFS v4 services in use with floating IPs"
fi
exit ${RETURN_CODE}
