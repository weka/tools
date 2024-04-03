#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for at most 16 NUMA regions for this host"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-342965"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

NUMBER_OF_NUMA_REGIONS=$(ls -d /sys/devices/system/node/node* | wc -l)

if [[ ${NUMBER_OF_NUMA_REGIONS} -gt 16 ]] ; then
    echo "There are ${NUMBER_OF_NUMA_REGIONS} NUMA regions"
    echo "Please see ${JIRA_REFERENCE} for more information"
    RETURN_CODE="254"
fi

exit ${RETURN_CODE}
