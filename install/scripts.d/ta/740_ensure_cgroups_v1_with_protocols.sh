#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Ensure cgroups v1 is available with a protocol server"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-297148"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    exit 254
elif [[ $? -eq 127 ]]; then
    echo "WEKA not found"
    exit 254
elif [[ $? -eq 41 ]]; then
    echo "Unable to login into Weka cluster."
    exit 254
fi

CURRENT_CGROUP_MODE=$(stat -fc %T /sys/fs/cgroup)

if [[ ${CURRENT_CGROUP_MODE} = "tmpfs" ]] ; then
    #No check required - cgroup v1 is in operation
    RETURN_CODE=0
else
    for CONTAINER in $(weka local ps --no-header | awk '{print $1}' | grep -w -e ganesha -e smbw -e s3) ; do
        RETURN_CODE=254
        echo "Protocol container ${CONTAINER} is not yet compatible with cgroup mode ${CURRENT_CGROUP_MODE}"
        echo "Recommended Resolution: reboot the host with cgroup v1 enabled, likely by adding"
        echo "\"systemd.unified_cgroup_hierarchy=false\" to e.g. /etc/default/grub's DEFAULT line and"
        echo "running \"update-grub\" (OS-dependent)"
    done
fi
    
if [[ ${RETURN_CODE} -eq 0 ]] ; then
    echo "Protocols (if any) are on cgroups v1"
fi

exit $RETURN_CODE
