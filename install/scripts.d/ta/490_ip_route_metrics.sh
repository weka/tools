#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if IP routing uses metrics"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

NUMBER_OF_ROUTES_WITH_METRICS=$(ip --json route | jq "[.[]|select(.metric!=null)]|length")

if [[ ${NUMBER_OF_ROUTES_WITH_METRICS} -gt "0" ]]; then
    RETURN_CODE="254"
    echo "Detected routing entries which specify a metric. It is possible"
    echo "that these entries will negatively affect the performance of e.g. floating IP"
    echo "addresses. In any case it is unlikely that preferential IP routes are of"
    echo "benefit in a high-performance local network"
fi

exit ${RETURN_CODE}
