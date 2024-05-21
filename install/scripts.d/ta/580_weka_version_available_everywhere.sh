#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if Weka agent version matches cluster version"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-364875"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

WEKA_CLUSTER_VERSION=$(weka status --json |  python3 -c 'import sys, json; data = json.load(sys.stdin) ; print(data["release"])')
CURRENT_AGENT_VERSION=$(weka version | grep '^*' | awk '{print $2}')
if [[ ${WEKA_CLUSTER_VERSION} != ${CURRENT_AGENT_VERSION} ]] ; then
    echo "The currently running cluster version ${WEKA_CLUSTER_VERSION} does not match the"
    echo " default installed local agent version ${CURRENT_AGENT_VERSION}"
    RETURN_CODE="254"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Weka local agent matches cluster running version"
fi

exit ${RETURN_CODE}
