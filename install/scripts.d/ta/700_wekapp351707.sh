#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check to see if affected by WEKAPP-351707"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-351707"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Per R&D:
#  A bug, introduced in 4.2.7 (WEKAPP-351707), blocks backpressure if writecache is below 50% of data on SSD.
#  An override exists, fs_backpressure_skip_ssdwritecache_estimation_all, that will block this check so data will be evicted to the OBS

# This issue should only affect 4.2.7.x - 4.2.8.x, as the fix, WEKAPP-368977, was introduced in 4.2.9.x.


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

WEKA_VERSION=$(weka version | grep -E ^\* | cut -d ' ' -f2)
if [[ $WEKA_VERSION = "4.2.7.64" || $WEKA_VERSION = "4.2.8.66" ]]; then
    while read AVAIL_SSD USED_SSD_META OBS; do
        # Only care about filesystems where there is an OBS
        if [[ -n $OBS ]]; then
            if [ $((USED_SSD_META * 100 / AVAIL_SSD)) -gt 50 ]; then
                RETURN_CODE=254
                echo "SSD metadata exceeds more than half of available SSD space on one or more filesystems."
                echo "Possibly vulnerable to WEKAPP-351707."
                echo "Consider adding the fs_backpressure_skip_ssdwritecache_estimation_all override."
            fi
        fi
    done < <(weka fs -R --no-header -o availableSSD,usedSSDM,stores | sed -e 's/B//g' | awk '{print $1, $2, $3}')
else
    echo "Weka version $WEKA_VERSION is not affected by WEPAPP-351707."
    exit 0
fi

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Not vulnerable to WEKAPP-351707."
fi

exit ${RETURN_CODE}
~                                                                                                          