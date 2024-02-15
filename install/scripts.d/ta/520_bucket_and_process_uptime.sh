#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if buckets have been rebooting"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# check if we can run weka commands
weka status &> /dev/null
status=$?
if [[ $status -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    if [[ $status -eq 127 ]]; then
        echo "WEKA not found"
    elif [[ $status -eq 41 ]]; then
        echo "Unable to log into Weka cluster"
    fi
    exit 254 # WARN
fi

MOST_RECENT_BUCKET_STARTTIME=$( date +%s --date=$(weka cluster bucket  --json -s -uptime | python3 -c 'import sys, json; data = json.load(sys.stdin) ; print(data[0]["up_since"])'))
MOST_RECENT_PROCESS_STARTTIME=$(date +%s --date=$(weka cluster process --json -s -uptime | python3 -c 'import sys, json; data = json.load(sys.stdin) ; print(data[0]["up_since"])'))
CURRENT_TIME=$(                 date +%s)

if [[ $((${CURRENT_TIME}-${MOST_RECENT_BUCKET_STARTTIME})) -lt 3600 ]]; then
    RETURN_CODE="254"
    echo "Weka buckets have been restarted within the last hour. This may not be a problem on a new cluster"
    echo "but could be indicative of problems (e.g. network flapping"
fi
if [[ $((${CURRENT_TIME}-${MOST_RECENT_PROCESS_STARTTIME})) -lt 3600 ]]; then
    RETURN_CODE="254"
    echo "Weka processes have been restarted within the last hour. This may not be a problem on a new cluster"
    echo "but could be indicative of problems (e.g. network flapping"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No weka buckets or processes have been restarted within the last hour"
fi
exit ${RETURN_CODE}
