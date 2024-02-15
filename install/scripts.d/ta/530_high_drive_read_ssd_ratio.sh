#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Ratio of NVMe read operations to DRIVE node read operations"
SCRIPT_TYPE="single"
JIRA_REFERENCE="WEKAPP-335035"
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

HIGHEST_EXPECTED_RATIO="3"
TIME_TO_EXAMINE="1h"
# TODO: should possibly change this to calculate the values rather than relying on the macro
HIGHEST_WITNESSED_RATIO=$(weka stats --show-internal --stat=DRIVE_READ_RATIO_PER_SSD_READ --start-time -${TIME_TO_EXAMINE} --output value -s value --no-header | tail -n1 | sed 's/[^.0-9]//g')

HIGHER_THAN_EXPECTED=$(awk "BEGIN { print (${HIGHEST_WITNESSED_RATIO} >= ${HIGHEST_EXPECTED_RATIO}) ? \"YES\" : \"NO\" }")

if [[ ${HIGHER_THAN_EXPECTED} == "YES" ]]; then
    RETURN_CODE="254"
    echo "The ratio of NVMe read requests vs DRIVE node read operations is higher than expected over the last ${TIME_TO_EXAMINE}"
    echo "This could indicate a number of things, such as splitting of read requests or perhaps read amplification"
    echo "Review ${JIRA_REFERENCE} for details"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "The ratio of NVMe read requests vs DRIVE node read operations is within expected limits over the last ${TIME_TO_EXAMINE}"
fi
exit ${RETURN_CODE}
