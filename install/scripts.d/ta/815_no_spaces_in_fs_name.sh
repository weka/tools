#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Verify no spaces in any filesystem name"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
    echo "ERROR: Not able to run Weka commands."
    exit 254
elif [[ $? -eq 127 ]]; then
    echo "Weka not found."
    exit 254
elif [[ $? -eq 41 ]]; then
    echo "Unable to login into Weka cluster."
    exit 254
fi

while read -r WEKA_FS_NAME ; do 
    if [[ ${WEKA_FS_NAME} = *" "* ]]; then
        echo "Filesystem \"${WEKA_FS_NAME}\" contains spaces"
        echo "This can prevent S3 buckets from being created"
        NEW_RECOMMENDED_NAME=$(echo ${WEKA_FS_NAME} | sed 's/ /_/g')
        echo "Recommended resolution: update the cluster name, e.g. using:"
        echo " weka fs update \"${WEKA_FS_NAME}\" --new-name ${NEW_RECOMMENDED_NAME}"
        RETURN_CODE=254
    fi
done < <(weka fs --no-header --output name)

if [[ $RETURN_CODE -eq 0 ]] ; then
    echo "No filesystem found with spaces in the name"
    exit 0
fi

exit ${RETURN_CODE}
