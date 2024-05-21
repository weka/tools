#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Confirm no Object Store is in scarce mode"
SCRIPT_TYPE="single"
JIRA_REFERENCE="WEKAPP-376458"
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

for OBS_ID in $(weka fs tier s3 --json | python3 -c 'import sys, json; data = json.load(sys.stdin) ; print("\n".join(obs["id"] for obs in data))') ; do
    OBS_ID_NUMERIC=$(echo ${OBS_ID} | sed 's/[^0-9]*//g')
    SCARCE_MODE=$(weka debug config show "obsBuckets[${OBS_ID_NUMERIC}]._scarceMode")
    if [[ ${SCARCE_MODE} == "true" ]] ; then
        RETURN_CODE="254"
        echo "The Object Store Bucket ${OBS_ID_NUMERIC} is in \"scarce\" mode, which may lead to problems flushing NVMe tiers"
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No Object Stores found in scarce mode"
fi

exit ${RETURN_CODE}
