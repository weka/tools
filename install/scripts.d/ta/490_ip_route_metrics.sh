#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if IP routing uses metrics"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

# check if the ip command supports --json
ip --json &> /dev/null
status=$?
if [[ $status -ne 0 ]]; then
    echo "ERROR: Not able to run ip --json command"
    if [[ $status -eq 127 ]]; then
        echo "ip command not found"
    fi
    exit 254 # WARN
fi

NUMBER_OF_ROUTES_WITH_METRICS=$(ip -4 --json route | python3 -c '
import sys, json
data = json.load(sys.stdin)
print(len([r for r in data if r.get("metric") and r["metric"]]))
')

if [[ ${NUMBER_OF_ROUTES_WITH_METRICS} -gt "0" ]]; then
    RETURN_CODE="254"
    echo "Detected routing entries which specify a metric. It is possible"
    echo "that these entries will negatively affect the performance of e.g. floating IP"
    echo "addresses. In any case it is unlikely that preferential IP routes are of"
    echo "benefit in a high-performance local network"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No IP routes found with metrics"
fi
exit ${RETURN_CODE}
