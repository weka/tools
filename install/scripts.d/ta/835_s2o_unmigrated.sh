#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if a filesystem is marked as downloaded in the snapViews."
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"

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

# Sample output
#  name:isDownloaded:noguid:00000000-0000-0000-0000-000000000000isDownloaded:noguid:00000000-0000-0000-0000-000000000000
#  name:fs1-snap2isDownloaded:yesguid:192c3fcd-71be-4b94-b7c6-4b39d3c06545isDownloaded:noguid:00000000-0000-0000-0000-000000000000

while read SNAPVIEW; do
    if [[ ${SNAPVIEW} =~ "name:"(.*)"isDownloaded:yesguid:"([[:alnum:]\-]+)"isDownloaded:" ]]; then
        FS_NAME=${BASH_REMATCH[1]}
        GUID=${BASH_REMATCH[2]}
        
        echo "WARN: Filesystem ${FS_NAME} may have been restored via Snap2Obj, but not migrated to its own bucket"
        echo " This filesystem was downloaded from the cluster with GUID ${GUID}"
        RETURN_CODE=254
    fi
done < <(weka debug config show snapViews | egrep -w '(name|isDownloaded|guid)' | paste - - - - - | tr -d \"\,[:blank:])

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No unmigrated Snap2Obj filesystems detected"
else
    echo "Recommended Resolution: perform a bucket migration, or a bucket detach, of the affected filesystems"
fi

exit ${RETURN_CODE}
