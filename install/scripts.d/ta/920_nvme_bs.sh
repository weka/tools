#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="NVME Block Size"
JIRA_REFERENCE="WEKAPP-468844"
SCRIPT_TYPE="single"

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

if [[ $(weka cluster drive -o block --no-header 2>/dev/null | sort -u | awk 'END { print NR }') -gt 1 ]]; then
    echo "WARN: Cluster drives with a mix of different block sizes was detected. This may have performance implications."
    echo "Recommended steps: if this is undesired, the drives will need to be deactivated, wait for the rebuild to complete,"
    echo " format the drives with the desired block size (if supported) and add the drives back to the cluster."
    RETURN_CODE=254
else
    echo "Cluster drives have a consistent block size."
fi

exit ${RETURN_CODE}