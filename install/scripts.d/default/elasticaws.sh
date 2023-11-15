#!/bin/bash

DESCRIPTION="Check if AWS Enhanced Networking is enabled"
SCRIPT_TYPE="parallel"

# Check if AWS Enhanced Networking is enabled, if not on AWS, script would return true (success)
set -x
if [ -d /etc/amazon ]; then
	echo "On Amazon AWS system, testing if enhanced networking is enabled and running"
	#modinfo ena
	modinfo ena | grep -i elastic &> /dev/null
	if [ $? -eq 1 ]; then
		echo "Enhanced networking is not supported on this AWS Amazon system"
		ret="1"
	else
		echo "Enhanced networking is supported and enabled"
		ret="0"
	fi
else
	echo "Not on Amazon AWS system, enhanced networking not tested"
	ret="0"
fi

exit $ret
