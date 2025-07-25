#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for RDMA network errors"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
REFERENCE="WEKAPP-494143"

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

NUMBER_OF_RDMA_ERRORS=$(weka stats --show-internal --stat RDMA_NET_ERR_RETRY_EXCEEDED,RDMA_BINDING_FAILOVERS,RDMA_SERVER_BINDING_RESTARTS,RDMA_COMP_FAILURES,RDMA_WAIT_TIMEOUT,RDMA_WAIT_TIMEOUT --start-time -10m -Z --no-header | wc -l)

if [[ "${NUMBER_OF_RDMA_ERRORS}" -ne "0" ]] ; then
    RETURN_CODE=254
    echo "Some RDMA errors were seen in the last 10 minutes; this almost always indicates a hardware or a network issue"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No RDMA problems detected"
else
    echo "Recommended steps: Review the output of:"
    echo " weka stats --show-internal --stat RDMA_NET_ERR_RETRY_EXCEEDED,RDMA_BINDING_FAILOVERS,RDMA_SERVER_BINDING_RESTARTS,RDMA_COMP_FAILURES,RDMA_WAIT_TIMEOUT,RDMA_WAIT_TIMEOUT --start-time -10m"
    echo " (perhaps with the --per-process flag to highlight individual WEKA processes)"
    echo "Also investigate network errors, in the case of an InfiniBand fabric, looking at ibqueryerrors, in particular"
    echo " check if PORT_XMIT_DISCARDS figure is rising rapidly"
fi


exit ${RETURN_CODE}
