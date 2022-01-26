#!/bin/bash

DESCRIPTION="Check if internet connection available..."
SCRIPT_TYPE="parallel"

# Checking if there is an internet connection available
ping -c2 -i1 -W 1 aws.amazon.com | grep -i "bytes from" &> /dev/null
if [ $? -eq 1 ]; then
	ping -c2 -i1 -W 1 -W 2 13.33.27.206 | grep -i "bytes from" &> /dev/null
	if [ $? -eq 1 ]; then
		write_log "Internet connection unavailable"
		ret="1"
	else
		write_log "Internet connection available, but DNS for some reason unresponsive"
		ret="0"
	fi
else
	write_log "Internet connection avialable"
	ret="0"
fi
	
exit $ret
