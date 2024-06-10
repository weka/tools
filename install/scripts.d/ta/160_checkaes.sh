#!/bin/bash

DESCRIPTION="Check if CPU has AES enabled and supported"
SCRIPT_TYPE="parallel"

ret="1"
# Check if current CPU has AES enabled and supported
grep -m1 -qw aes /proc/cpuinfo
if [[ $? -eq 0 ]]; then
	echo "$(hostname) CPU supports AES and it is enabled"
	ret="0"
else
	echo "$(hostname) CPU doesn't have AES supported or enabled"
	ret="1"
fi

exit $ret
