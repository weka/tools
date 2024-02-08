#!/bin/bash

#set -ue # Fail with an error code if there is any sub-command/variable error

DESCRIPTION="Log the running of TA-Tool"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"

RETURN_CODE=0
weka events trigger-event "WEKA TA-Tool has been run: ta-tool_launched"
echo "WEKA TA-Tool has been run: ta-tool_launched"
exit ${RETURN_CODE}
