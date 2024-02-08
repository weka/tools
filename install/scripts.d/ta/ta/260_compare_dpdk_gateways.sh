#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Compare DPDK gateway settings"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel-compare-backends"


(
for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header); do
    if [[ ( ${WEKA_CONTAINER} == "ganesha" ) || \
          ( ${WEKA_CONTAINER} == "samba" )   || \
          ( ${WEKA_CONTAINER} == "smb"   ) ]] ; then
        continue
    fi
    sudo weka local resources --container ${WEKA_CONTAINER} --json | jq -r "[.net_devices[].gateway] | .[]" | sort -n
done
) | sha256sum | awk '{print $1}'
