#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for statistic outliers"
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
# "statistic name;interval in seconds over which to check ; Maximum multiples of standard deviation permitted; WTA Reference; SFDC reference"
# All values are required
declare -a CONTAINER_LEVEL_STATISTICS

CONTAINER_LEVEL_STATISTICS+=("PUMPS_TXQ_FULL;600;10;  ; ")

AWK_TEMP_FILE=$(mktemp)
cat <<'EOSTDDEVAWK' > ${AWK_TEMP_FILE}
#!/usr/bin/awk -f

BEGIN {
    lowest_value_seen  = 0
    highest_value_seen = 0
}
{
    # Read each number into the array x
    x[NR] = $1
    sum += $1
    if ( $1 > highest_value_seen) { highest_value_seen = $1 }
    if ( $1 < lowest_value_seen)  { lowest_value_seen  = $1 }
}

END {
    n = NR

    # Compute the mean
    mean = sum / n

    # Compute the standard deviation - assuming sample rather than population as
    # this is partial data from a time interval
    for (i = 1; i <= n; i++) {
        sumsq += (x[i] - mean)^2
    }
    variance = sumsq / (n - 1)  # sample rather than entire population
    stddev   = sqrt(variance)

    # Print the results
    printf "STDDEV=%.2f\n", stddev
    printf "VARIANCE=%.9f\n", variance
    printf "LOWEST_VALUE_SEEN=%.2f\n", lowest_value_seen
    printf "HIGHEST_VALUE_SEEN=%.2f\n", highest_value_seen
}
EOSTDDEVAWK


for STATISTIC_TO_CHECK in "${CONTAINER_LEVEL_STATISTICS[@]}" ; do
    STATISTIC_NAME=$( echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $1}')
    INTERVAL=$(       echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $2}')
    MAX_STDDEV=$(     echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $3}')
    WTA_REFERENCE=$(  echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $4}')
    KB_REFERENCE=$(   echo ${STATISTIC_TO_CHECK} | awk -F';' '{print $5}')

    # Only check DRIVES and COMPUTE for most of these
    BACKEND_PROCESSES=$( ( weka cluster process -o id -F role=COMPUTE --no-header ; weka cluster process -o id -F role=DRIVES --no-header ) | paste -sd "," - )

    eval $(weka stats --show-internal --stat ${STATISTIC_NAME} --per-process --interval ${INTERVAL} -s value --no-header -o  value -R --process-ids ${BACKEND_PROCESSES} | sed 's/[^0-9\.]//g' |  awk -f ${AWK_TEMP_FILE})
    HIGHEST_VALUE_SEEN_INT="$(printf '%d' ${HIGHEST_VALUE_SEEN}              2> /dev/null)"
    STDDEV_INT="$(            printf '%d' ${STDDEV}                          2> /dev/null)"
    MAX_VARIATION_INT="$(     printf '%d' $((${STDDEV_INT}*${MAX_STDDEV}))   2> /dev/null)"
    if [[ ${HIGHEST_VALUE_SEEN_INT} -gt ${MAX_VARIATION_INT} ]]; then
        echo "The Weka container-level statistic ${STATISTIC_NAME} showed some statistical outliers"
        echo "This is based on the data having a standard deviation of ${STDDEV}, and the highest value seen"
        echo "${HIGHEST_VALUE_SEEN} which is beyond the arbitrary limit standard_deviation *  ${MAX_STDDEV}"
        echo "This is not conclusive evidence of a problem, however it may be useful as a pointer"
        echo "The data checked is from weka stats --show-internal --stat ${STATISTIC_NAME} --per-process --interval ${INTERVAL} -s value --no-header -o  value -R  --process-ids ${BACKEND_PROCESSES}"
        RETURN_CODE=254
    fi
done



if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No known-significant statistical outliers detected"
fi
exit ${RETURN_CODE}
