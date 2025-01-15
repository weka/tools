#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Enforce heartbeat_grace_msec is greater than cluster_lease"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"

RETURN_CODE=0


HB_GRACE_DEFAULT=$(  weka debug override list-keys --filter key=heartbeat_grace_msecs       --output defaultValue --no-header | head -n1)
CL_TIMEOUT_DEFAULT=$(weka debug override list-keys --filter key=cluster_lease_timeout_msecs --output defaultValue --no-header | head -n1)
HB_GRACE_MANUAL=$(   weka debug override list      --filter key=heartbeat_grace_msecs       --output value        --no-header)
CL_TIMEOUT_MANUAL=$( weka debug override list      --filter key=cluster_lease_timeout_msecs --output value        --no-header)
HB_GRACE=${HB_GRACE_MANUAL:-${HB_GRACE_DEFAULT}}
CL_TIMEOUT=${CL_TIMEOUT_MANUAL:-${CL_TIMEOUT_DEFAULT}}

# enforce heartbeat_grace_msecs > cluster_lease_timeout_msecs
if [[ ${CL_TIMEOUT} -ge ${HB_GRACE} ]]; then
    echo "WARN: cluster_lease_timeout_msecs (${CL_TIMEOUT}) is greater than or equal to heartbeat_grace_msecs (${HB_GRACE})"
    echo "This may be because one value has been left at a default, but this configuration"
    echo "might prevent cluster status being propagated correctly."
    echo "To rectify, ensure that heartbeat_grace_msecs is greater than cluster_lease_timeout_msecs"
    RETURN_CODE=254
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "heartbeat_grace_msecs is greater than cluster_lease_timeout_msecs"
fi

exit ${RETURN_CODE}
