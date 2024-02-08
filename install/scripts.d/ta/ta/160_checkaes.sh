#!/bin/bash

DESCRIPTION="Check if CPU has AES enabled and supported"
SCRIPT_TYPE="parallel"

ret="1"
# Check if current CPU has AES enabled and supported
res=`grep -m1 -o aes /proc/cpuinfo`
if [ -z $res ]; then
	echo "`hostname` CPU doesn't have AES supported or enabled"
	ret="1"
else
	echo "`hostname` CPU supports AES and it is enabled"
	ret="0"
fi

exit $ret
