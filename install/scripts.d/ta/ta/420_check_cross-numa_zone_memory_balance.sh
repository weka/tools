#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that NUMA zones have similar amounts of memory"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""

RETURN_CODE=0

MIN_MEMORY_SEEN=$(grep MemTotal /sys/devices/system/node/node*/meminfo | sort -nk4 | head -n 1)
MAX_MEMORY_SEEN=$(grep MemTotal /sys/devices/system/node/node*/meminfo | sort -nk4 | tail -n 1)


MAX_ALLOWED_RATIO=1008 # this translates to 8 percent, due to bash maths

# Compare the highest and lowest amount of memory seen across NUMA regions
MAX_MEMORY_SEEN_KB=$(echo ${MAX_MEMORY_SEEN} | awk '{print $4}')
MIN_MEMORY_SEEN_KB=$(echo ${MIN_MEMORY_SEEN} | awk '{print $4}')

MAX_MEMORY_SEEN_ZONE=$(echo ${MAX_MEMORY_SEEN} | awk -F: '{print $1}')
MIN_MEMORY_SEEN_ZONE=$(echo ${MIN_MEMORY_SEEN} | awk -F: '{print $1}')

# and then calculate the ratio between the two, doing floating-point maths in bash, but scaling it by 10^3
RATIO_SEEN=$(printf "%d\n" $((10**3 * $MAX_MEMORY_SEEN_KB/$MIN_MEMORY_SEEN_KB)))
if [[ ${RATIO_SEEN} -gt ${MAX_ALLOWED_RATIO} ]]; then
    RETURN_CODE=254
    echo "The total memory reported in the two different NUMA regions ${MAX_MEMORY_SEEN_ZONE}"
    echo "and ${MIN_MEMORY_SEEN_ZONE} differs by more than the expected"
    echo "ratio. This might not cause a problem, but it can e.g. prevent Weka processes"
    echo "from starting due to lack of NUMA zone-local memory"
    
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "NUMA zones have similar amounts of memory"
fi
exit ${RETURN_CODE}
