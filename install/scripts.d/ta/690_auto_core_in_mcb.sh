#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Warn about auto-core allocation in MCB"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="https://wekaio.slack.com/archives/C01RYT54NP4/p1717722025876539"
RETURN_CODE=0

# find all the local containers which match MCB names
for WEKA_CONTAINER in $(weka local ps --output name --no-header | grep -E '(drives|compute|frontend)[0-9]') ; do
    MATCHES=$(weka local resources -C ${WEKA_CONTAINER} | grep -cE '^(DRIVES|COMPUTE|FRONTEND)  *[0-9].*auto')
    if [[ ${MATCHES} -ne 0 ]] ; then
        echo "Host ${HOSTNAME} has auto-core allocation in MCB container ${WEKA_CONTAINER}"
        exit 254
    fi
done

echo "No auto-allocated MCB CPUs"
exit 0
