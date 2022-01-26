#!/bin/bash

DESCRIPTION="Check if CPU has AES enabled and supported"
SCRIPT_TYPE="parallel"

# Check if current CPU has AES enabled and supported
res=`grep -m1 -o aes /proc/cpuinfo`
if [ -z $res ]; then
	write_log "Running CPU doesn't have AES supported or enabled"
	ret="1"
else
	write_log "Running CPU has AES supported and enabled"
	ret="0"
fi

exit $ret
