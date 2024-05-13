#!/bin/bash

DESCRIPTION="Check if internet connection available..."
SCRIPT_TYPE="parallel"

# Checking if there is an internet connection available
ping -4 -c2 -i1 -W 1 aws.amazon.com | grep -i "bytes from" &> /dev/null
if [ $? -eq 1 ]; then
	ping -4 -c2 -i1 -W 1 -W 2 13.33.27.206 | grep -i "bytes from" &> /dev/null
	if [ $? -eq 1 ]; then
		echo "Internet connection unavailable"
		ret="254"
	else
		echo "Internet connection available, but DNS for some reason unresponsive"
		ret="254"
	fi
else
	echo "Internet connection available"
	ret="0"
fi
	
exit $ret
