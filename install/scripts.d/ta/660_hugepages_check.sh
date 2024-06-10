#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for hugepages memory allocation discrepancy"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# NOTE: A test warning is not indicative of a problem. Further investigation would be warranted.

HUGE_1G=$(cat /sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages)
HUGE_2M=$(cat /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages)

WEKA_HUGE_1G=$(awk -F "=" '/weka/ && /huge/{print $NF}' /proc/*/numa_maps | grep -c 1048576)
WEKA_HUGE_2M=$(awk -F "=" '/weka/ && /huge/{print $NF}' /proc/*/numa_maps | grep -c 2048)

if [[ -z $WEKA_HUGE_1G && -z $WEKA_HUGE_2M ]]; then
    echo "Unable to determine weka hugepage allocation."
    exit ${RETURN_CODE}
fi

if [[ -n $WEKA_HUGE_1G ]]; then
    DIFF_1G=$((HUGE_1G - WEKA_HUGE_1G))

    if [[ $DIFF_1G != 0 ]]; then
      RETURN_CODE=254
      echo "Discrepancy of $DIFF_1G 1GiB hugepage(s) between Weka and OS."
    fi
fi

if [[ -n $WEKA_HUGE_2M ]]; then
    DIFF_2M=$((HUGE_2M - WEKA_HUGE_2M))

    if [[ $DIFF_2M != 0 ]]; then
        RETURN_CODE=254
        echo "Discrepancy of $DIFF_2M 2MiB hugepage(s) between Weka and OS."
    fi
fi


if [[ $RETURN_CODE -eq 0 ]]; then
    echo "No hugepages allocation discrepancy."
fi

exit ${RETURN_CODE}