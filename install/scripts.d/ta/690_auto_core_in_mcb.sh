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
        echo "Recommended Resolution: reconfigure the local resources to use a fixed CPU core, such as"
        if [[ ${WEKA_CONTAINER} =~ "drive" ]] ; then 
            echo "weka local resources cores --container ${WEKA_CONTAINER} <NUMBER-OF-CORES> --only-drives-cores --core-ids X,Y,Z"
        elif [[ ${WEKA_CONTAINER} =~ "compute" ]] ; then 
            echo "weka local resources cores --container ${WEKA_CONTAINER} <NUMBER-OF-CORES> --only-compute-cores --core-ids X,Y,Z"
        elif [[ ${WEKA_CONTAINER} =~ "frontend" ]] ; then 
            echo "weka local resources cores --container ${WEKA_CONTAINER} <NUMBER-OF-CORES> --only-frontend-cores --core-ids X,Y,Z"
        fi
        exit 254
    fi
done

echo "No auto-allocated MCB CPUs"
exit 0
