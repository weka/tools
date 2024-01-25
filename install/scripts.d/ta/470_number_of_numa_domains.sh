#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for more than supported number of NUMA domains"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-342965"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

MAXIMUM_NUMA_DOMAINS="16" # as of 4.2.7

NUMBER_OF_NUMA_DOMAINS=$(ls -d /sys/devices/system/node/node* |wc -l)

if [[ ${NUMBER_OF_NUMA_DOMAINS} -gt ${MAXIMUM_NUMA_DOMAINS} ]]; then
    echo "Found ${NUMBER_OF_NUMA_DOMAINS} NUMA domains, which is greater than the current maximum of ${MAXIMUM_NUMA_DOMAINS}"
    RETURN_CODE=254
fi

exit ${RETURN_CODE}
