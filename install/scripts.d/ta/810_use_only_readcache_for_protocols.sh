#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Ensure any protocols are using only readcache mounts"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-444847"

RETURN_CODE=0

for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header | grep -w -e ganesha -e samba -e smbw -e s3); do
    MOUNTS_USING_WRITECACHE=$(sudo weka local exec --container ${WEKA_CONTAINER} mount -t wekafs | grep -c writecache)
    if [[ ${MOUNTS_USING_WRITECACHE} != "0" ]]; then
        echo "WARN: container ${WEKA_CONTAINER} - used for protocols - is using writecache on host ${HOSTNAME}"
        echo "Refer to ${JIRA_REFERENCE} for more details"
        if [[ ${WEKA_CONTAINER} =~ "s3" ]]; then
            echo "Recommended Resolution: for s3, use the following (brief service interruption):"
            echo " weka s3 cluster update --mount-options readcache -f"
        elif [[ ${WEKA_CONTAINER} =~ "smb" ]]; then
            echo "Recommended Resolution: for smb, for each share, delete it and re-add it (service interruption)"
        elif [[ ${WEKA_CONTAINER} =~ "ganesha" ]]; then
            echo "Recommended Resolution: for NFS, for each share, delete it and re-add it (service interruption)"
        fi
        
        RETURN_CODE=254
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No protocols are using writecache"
fi

exit ${RETURN_CODE}
