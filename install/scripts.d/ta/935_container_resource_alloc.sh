#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for inconsistent container resources"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""

RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
RC=$?

case ${RC} in
    254)
        echo "ERROR: Not able to run weka commands."
        exit 254
        ;;
    127)
        echo "WEKA not found."
        exit 254
        ;;
    41)
        echo "Unable to login to Weka cluster."
        exit 254
        ;;
esac

while read WEKA_CONTAINER; do
    # Core consistency check
    if [[ $(weka cluster container -b -F container=${WEKA_CONTAINER} -o cores --no-header | uniq -c | wc -l) -gt 1 ]]; then
        echo "WARN: There is a discrepancy in the number of cores allocated to the ${WEKA_CONTAINER} containers."
        echo "Core discrepancies between the same containers is atypical -- please ensure this was intentional."
        echo "If not, it is recommended to configure a consistent number of cores between similar containers."
        RETURN_CODE=254
    fi

    # Memory consistency check
    MAX_MEM=$(weka cluster container -b -F container=${WEKA_CONTAINER} -o memory --no-header | sort -u | tail -n1 | awk '{print $1}')
    MIN_MEM=$(weka cluster container -b -F container=${WEKA_CONTAINER} -o memory --no-header | sort -u | head -n1 | awk '{print $1}')

    if [[ $MIN_MEM != $MAX_MEM ]]; then
        PERCENT_DIFF=$(awk -v min="$MIN_MEM" -v max="$MAX_MEM" 'BEGIN { printf "%.0f", (((max - min) / max) * 100) }')
        if [[ $PERCENT_DIFF -gt 5 ]]; then
            echo "WARN: There is a $PERCENT_DIFF% difference between the minimum and maximum amount of hugepages memory allocated between the $WEKA_CONTAINER containers."
            echo "Memory discrepancies between the same containers is atypical -- please ensure this was intentional."
            echo "If not, it is recommended to configure a consistent amount of memory between similar containers."
            RETURN_CODE=254
        fi
    fi
done < <(weka cluster container -b -o container --no-header | awk '/compute|drive|frontend/' | sort -u)


if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No significant container resource discrepancies."
fi

exit $RETURN_CODE
