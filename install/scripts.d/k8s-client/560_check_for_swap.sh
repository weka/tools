#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if swap exists"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="SFDC-12738"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0


SWAPTOTAL=$(grep SwapTotal /proc/meminfo  | awk '{print $2}')
if [[ ${SWAPTOTAL} -ne "0" ]] ; then
    echo "This host has swap configured - this is unlikely to be"
    echo "helpful in a large memory system"
    echo "Recommended Resolution: if the host has enough RAM, disable swap with swapoff then disable swap at boot time (likely in /etc/fstab)"
    RETURN_CODE="254"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No swap found - this is a good thing"
fi

exit ${RETURN_CODE}
