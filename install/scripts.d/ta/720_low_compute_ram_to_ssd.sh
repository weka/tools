#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check to compare the available COMPUTE ram to SSD capacity"
SCRIPT_TYPE="single"
JIRA_REFERENCE="WEKAPP-405324"
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

WEKA_COMPUTE_RAM=$(weka cluster process -F role=COMPUTE --output memory --no-header --raw-units | awk '{tot+=$1} ; END {print tot}')
WEKA_SSD_CAPACITY=$(weka cluster drive --no-header --raw-units --output size | awk '{tot+=$1} ; END {print tot}')
RAM_TO_SSD_RATIO=$(echo "${WEKA_SSD_CAPACITY}/${WEKA_COMPUTE_RAM}" | bc)

# 4000 is a cautious ratio, likely sufficient to handle loss of hot-spare
if [[ ${RAM_TO_SSD_RATIO} -gt 4000 ]]; then
    echo "Warning: there is more than 4000 times the RAM capacity in total NVME capacity"
    echo "This may lead to Weka bucket startup issues. Refer to ${JIRA_REFERENCE}"
    echo "Recommended Resolution: add more memory to cluster - options include:"
    echo " . Increasing the amount of memory allocated to COMPUTE processes if there's spare"
    echo " . Increasing the amount RAM installed, then doing the above"
    echo " . Scaling out by adding more hosts"
    echo " . Reducing the size of the NVME by removing drives or tiering to Object Store"
    RETURN_CODE=254
else
    echo "RAM to SSD ratio is acceptable"
fi

exit ${RETURN_CODE}
