#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if Weka is using an excessive amount of total system memory."
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0


RSS=$(ps -o rsz -C wekanode | awk '{sum+=$1};END {print sum/1024/1024}')
HUGEPAGES=$(ls -la /opt/weka/data/agent/containers/state/*/huge{,1G}/* | awk '{hugepages+=$5}; END {print hugepages/1024/1024/1024}')

TOTAL_SYS=$(free -g | awk '/Mem/{print $2}')
TOTAL_NON_WEKA=$(awk -v v1=$RSS -v v2=$HUGEPAGES -v v3=$TOTAL_SYS 'BEGIN {print int(v3-(v1+v2))}')

if [[ ${TOTAL_NON_WEKA} -lt 8 ]]; then
    echo "WARN: Less than 8 GiB (${TOTAL_NON_WEKA} GiB) of memory free for non-Weka related processes"
    echo "Recommended Resolution: review the system memory requirements at docs.weka.io"
    RETURN_CODE=254
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "More than 8 GiB (${TOTAL_NON_WEKA} GiB) of memory not allocated to Weka"
fi

exit ${RETURN_CODE}
