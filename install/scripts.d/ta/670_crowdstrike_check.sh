#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for CrowdStrike Falcon Sensor"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# This endpoint protection has been shown to cause issues with the unloading
# of the wekafs kernel modules.

if systemctl status falcon-sensor &> /dev/null; then
    echo "Warning: CrowdStrike Falcon Sensor is running"
    echo "Recommended Resolution: we do not recommend using this software in conjunction with WEKA as"
    echo "it has been shown to cause problems unloading kernel modules"
    exit 254
elif lsmod | grep -q -m 1 falcon_lsm; then
    echo "Warning: Crowdstrike Falcon kernel module loaded"
    echo "Recommended Resolution: we do not recommend using this software in conjunction with WEKA as"
    echo "it has been shown to cause problems unloading kernel modules"
    exit 254
fi
echo "CrowdStrike Falcon Sensor is not running"
exit 0
