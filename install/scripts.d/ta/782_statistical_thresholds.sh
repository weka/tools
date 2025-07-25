#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for statistics breaching known-good thresholds"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""

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

#An array of strings (because bash can't do AoA). Each string is defined as:
# "statistic name;interval in seconds over which to check ; test to apply ; threshold"
declare -a CONTAINER_LEVEL_STATISTICS

CONTAINER_LEVEL_STATISTICS+=("GOODPUT_RX_RATIO;600;minimum;95;",   # need to keep the trailing semicolon
                             "GOODPUT_TX_RATIO;600;minimum;95;")

for STATISTIC_TO_CHECK in "${CONTAINER_LEVEL_STATISTICS[@]}" ; do
    STATISTIC_NAME=$( echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $1}')
    INTERVAL=$(       echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $2}')
    TEST_TO_APPLY=$(  echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $3}')
    THRESHOLD=$(      echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $4}')

    # Only check DRIVES and COMPUTE for most of these
    BACKEND_PROCESSES=$( ( weka cluster process -o id -F role=COMPUTE --no-header ; weka cluster process -o id -F role=DRIVES --no-header ) | paste -sd "," - )

    if [[ ${TEST_TO_APPLY} == "minimum" ]]; then
        # annoyingly disconnected processes show up as "0" - filter those out with -Z
        LOWEST_VALUE_SEEN=$(weka stats --show-internal --stat ${STATISTIC_NAME} -Z --per-process --interval ${INTERVAL} -s value --no-header -o  value -R --process-ids ${BACKEND_PROCESSES} | sed 's/[^0-9\.]//g' | sort -g | head -n 1)
        WORTH_EXAMINING=$(awk -v lowest=${LOWEST_VALUE_SEEN=} -v threshold=${THRESHOLD} 'BEGIN {if (lowest < threshold) print "Examine"; else print "Skip";}')
        if [[ ${WORTH_EXAMINING} == "Examine" ]]; then
            echo "The Weka container-level statistic ${STATISTIC_NAME} is below the established threshold of ${THRESHOLD}"
            echo "on at least some containers, with the lowest value seen being ${LOWEST_VALUE_SEEN}"
            echo "This is not conclusive evidence of a problem, however it may be useful as a pointer"
            echo "The data checked is from weka stats --show-internal --stat ${STATISTIC_NAME} --per-process --interval ${INTERVAL} -s value --no-header -o  value -R --process-ids ${BACKEND_PROCESSES}"
            RETURN_CODE=254
        fi
    elif [[ ${TEST_TO_APPLY} == "maximum" ]]; then
        HIGHEST_VALUE_SEEN=$(weka stats --show-internal --stat ${STATISTIC_NAME} --per-process --interval ${INTERVAL} -s value --no-header -o  value -R --process-ids ${BACKEND_PROCESSES} | sed 's/[^0-9\.]//g' | sort -g | head -n 1)
        WORTH_EXAMINING=$(awk -v highest=${HIGHEST_VALUE_SEEN=} -v threshold=${THRESHOLD} 'BEGIN {if (highest > threshold) print "Examine"; else print "Skip";}')
        if [[ ${WORTH_EXAMINING} == "Examine" ]]; then
            echo "The Weka container-level statistic ${STATISTIC_NAME} is above the established threshold of ${THRESHOLD}"
            echo "on at least some containers, with the highest value seen being ${HIGHEST_VALUE_SEEN}"
            echo "This is not conclusive evidence of a problem, however it may be useful as a pointer"
            echo "The data checked is from weka stats --show-internal --stat ${STATISTIC_NAME} --per-process --interval ${INTERVAL} -s value --no-header -o  value -R --process-ids ${BACKEND_PROCESSES}"
            RETURN_CODE=254
        fi
    fi
done



if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No known-significant statistical outliers detected"
fi
exit ${RETURN_CODE}
