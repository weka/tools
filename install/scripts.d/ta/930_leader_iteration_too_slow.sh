#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Cluster Leader Iteration too slow"
JIRA_REFERENCE="WEKAPP-513421"
SFDC_REFERENCE="https://wekaio.lightning.force.com/lightning/r/Knowledge__kav/ka0Qr0000007fmPIAQ/view"
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

if [[ $(weka events --type-list LeaderIterationTooSlow --show-internal --no-header --start-time -1d 2>/dev/null| wc -l) -ge 1 ]]; then
    echo "WARN: Cluster has experienced LeaderIterationTooSlow - if there are indications of"
    echo " performance problems please contact Customer Success and provide them the following"
    echo " references: ${JIRA_REFERENCE} and ${SFDC_REFERENCE}"
    RETURN_CODE=254
else
    echo "No LeaderIterationTooSlow found"
fi

exit ${RETURN_CODE}
