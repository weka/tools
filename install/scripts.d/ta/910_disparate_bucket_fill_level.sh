#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for disparity in Weka bucket fill level"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"
REFERENCE="WEKAPP-488736"

RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
RC=$?

case ${RC} in
    254)
        echo "ERROR: Not able to run weka commands."
        exit 254
        ;;
    127)
        echo "WEKA not found."
        exit 254
        ;;
    41)
        echo "Unable to login to Weka cluster."
        exit 254
        ;;
esac

MOST_FULL_BUCKET=$( weka cluster bucket -o fillLevel -s  fillLevel --no-header | tail -n 1 | sed s/[^.0-9]*//g)
LEAST_FULL_BUCKET=$(weka cluster bucket -o fillLevel -s -fillLevel --no-header | tail -n 1 | sed s/[^.0-9]*//g)

# If it's less than 10% full, not worth looking at because there's probably a disparity anyway
WORTH_EXAMINING=$(awk -v most_full=${MOST_FULL_BUCKET} 'BEGIN {if (most_full < 10) print "Skip"; else print "Examine";}')
if [[ "${WORTH_EXAMINING}" == "Examine" ]] ; then
    if [[ "${LEAST_FULL_BUCKET}" == "0" ]] ; then
        LEAST_FULL_BUCKET="0.1"                    # clumsily avoid divide by zero risk
    fi
    RESULT=$(awk -v most_full=${MOST_FULL_BUCKET} -v least_full=${LEAST_FULL_BUCKET} 'BEGIN { if((most_full / least_full)>1.5) print "Disparity"; else print "Normal";}')
    if [[ "${RESULT}" == "Disparity" ]] ; then
        RETURN_CODE=254
        echo "The ratio of Weka bucket min:max fill levels is more than 1.5 - this could lead to slow writes as space runs out"
    fi
fi
DANGEROUSLY_FULL=$(awk -v most_full=${MOST_FULL_BUCKET} 'BEGIN {if (most_full > 95) print "Warn"; else print "Safe";}')
if [[ "${DANGEROUSLY_FULL}" == "Warn" ]] ; then
    RETURN_CODE=254
    echo "At least one Weka bucket is more than 95% full - this could indicate a cluster struggling for usable RAID capacity"
fi
    
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No problems detected"
else
    echo "Recommended resolution: Increase NVME capacity or add tiering, or contact Weka Customer Success"
fi


exit ${RETURN_CODE}
