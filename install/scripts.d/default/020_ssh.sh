#!/bin/bash

DESCRIPTION="Check ssh to all hosts"
# script type is single, parallel, or sequential
SCRIPT_TYPE="single"


# Put your stuff here

let ERRORS=0
#
# check passwordless ssh connectivity, if given hostnames/ips on command line
#   this is no longer strictly required.
#
if [ $# -gt 0 ]; then
	for i in $*
	do
		ssh -o PasswordAuthentication=no  -o BatchMode=yes -o StrictHostKeyChecking=no $i exit &>/dev/null
		if [ $? -eq 0 ];
		then
			echo "Host $i ssh test passed"
		else
			echo "Host $i ssh test failed. Please correct the issue(s) and re-run this tool"
			let ERRORS=$ERRORS+1
		fi
	done
else
	echo "No hosts specified, skipping ssh connectivity test."
fi

echo "There were $ERRORS failures"

if [ $ERRORS -gt 0 ]; then
	ret=255		# HARDFAIL - if we can't ssh to all the servers, we can't continue
fi

exit 0
