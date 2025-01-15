#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check to verify no spaces in cluster name"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="KB-1191"
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

WEKA_CLUSTER_NAME=$(weka status | grep cluster: | sed -e 's/^ *cluster: *//' -e 's/ ([^)]*)$//')

if [[ ${WEKA_CLUSTER_NAME} = *" "* ]]; then
    echo "Weka cluster name contains spaces"
    echo "This will prevent an S3 cluster from starting - see KB ${KB_REFERENCE}"
    NEW_RECOMMENDED_NAME=$(echo ${WEKA_CLUSTER_NAME} | sed 's/ /_/g')
    echo "Recommended resolution: update the cluster name, e.g. using:"
    echo " weka cluster update --cluster-name ${NEW_RECOMMENDED_NAME}"
    RETURN_CODE=254
else
    echo "Weka cluster name does not contain spaces"
fi


exit ${RETURN_CODE}
