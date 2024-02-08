#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for disparate drive write latencies"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
JIRA_REFERENCE="WEKAPP-329809"
WTA_REFERENCE="WTA 08312023"
KB_REFERENCE="KB 1182"

RETURN_CODE=0


LOWEST_WRITE_LATENCY=$( weka stats --category ssd --stat DRIVE_WRITE_LATENCY --param "disk:*" --interval 60 -s value --output value --no-header | head -n1 | sed "s/[^0-9.]//g")
HIGHEST_WRITE_LATENCY=$(weka stats --category ssd --stat DRIVE_WRITE_LATENCY --param "disk:*" --interval 60 -s value --output value --no-header | tail -n1 | sed "s/[^0-9.]//g")

ALLOWABLE_MAGNITUDE=10

# we almost certainly have awk if not bc/dc
MULTIPLIED_LOWEST_LATENCY=$(awk -v "mag=${ALLOWABLE_MAGNITUDE}" -v "val=${LOWEST_WRITE_LATENCY}" 'BEGIN{out=(mag*val); print out;}')

#can't compare floats in bash
greater_than() {
    local FUNC_RETURN=1
    OUTPUT=$(awk -v n1="$1" -v n2="$2" 'BEGIN {printf (n1>n2?"TRUE":"FALSE") }')
    if [ ${OUTPUT} == "TRUE" ] ; then
        FUNC_RETURN=0
    fi
    echo ${FUNC_RETURN}
}

DISPARATE_WRITE_LATENCIES=$(greater_than ${HIGHEST_WRITE_LATENCY} ${MULTIPLIED_LOWEST_LATENCY})
if [[  ${DISPARATE_WRITE_LATENCIES} == 0 ]]; then
    RETURN_CODE=1
    echo "The current highest measured drive latency ${HIGHEST_WRITE_LATENCY} is greater than ${ALLOWABLE_MAGNITUDE} * the"
    echo "lowest measured latency (${LOWEST_WRITE_LATENCY}). This may indicate that you are affected by "
    if [[ ! -z "${WTA_REFERENCE}" ]]; then
        echo "${JIRA_REFERENCE}, discussed in ${WTA_REFERENCE}, SFDC ${KB_REFERENCE}"
    else
        echo "${JIRA_REFERENCE}, SFDC ${KB_REFERENCE}"
    fi
    echo "This does not necessarily prove a problem, and should be investigated"
fi
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No disparate drive write latencies"
fi
exit ${RETURN_CODE}
