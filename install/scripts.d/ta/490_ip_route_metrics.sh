#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if IP routing uses metrics with the same destination"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

# check if the ip command supports --json
ip --json addr &> /dev/null
status=$?
if [[ $status -ne 0 ]]; then
    echo "ERROR: Not able to run ip --json addr command"
    if [[ $status -eq 127 ]]; then
        echo "ip command not found"
    fi
    exit 254 # WARN
fi

# First find any routes that specify a route metric, then count them based
# on the same routing destination. A single route to a destination with
# a metric is fine (because the metric is meaningless there), but routes
# which specify the same destination *and* a metric is not likely to be useful.
#  (There are circumstances where it makes sense, such as a backup/failover
#   route that's not intended to be preferred)
NUMBER_OF_OVERLAPPING_ROUTES_WITH_METRICS=$(ip -4 --json route | python3 -c '
import sys, json
data = json.load(sys.stdin)

overlappingRoutesWithMetric = {}

for r in data:
    if r.get("metric") and r["metric"]:
        overlappingRoutesWithMetric[r["dst"]] = overlappingRoutesWithMetric.get(r["dst"], 0) + 1

if overlappingRoutesWithMetric:
    print(max(overlappingRoutesWithMetric.values()))
')

if [[ ${NUMBER_OF_OVERLAPPING_ROUTES_WITH_METRICS} -gt "1" ]]; then
    RETURN_CODE="254"
    echo "Detected more than 1 overlapping routing entries which specify a metric. It is possible"
    echo "that these entries will negatively affect the performance of e.g. floating IP"
    echo "addresses. In any case it is unlikely that preferential IP routes are of"
    echo "benefit in a high-performance local network"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No IP routes found with metrics"
fi
exit ${RETURN_CODE}
