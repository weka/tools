#!/bin/bash

DESCRIPTION="Check if HT/AMT is disabled"
SCRIPT_TYPE="parallel"

ret="0"
# Checking if CPU has HyperThreading available and running or disabled
which dmidecode &> /dev/null
if [ $? -eq 1 ]; then
	echo "Dmidecode tool wasn't found, could not test HyperThreading properly"
	ret="0"
else
	nproc=$(grep -i "processor" /proc/cpuinfo | sort -u | wc -l)
	phycore=$(cat /proc/cpuinfo | egrep "core id|physical id" | tr -d "\n" | sed s/physical/\\nphysical/g | grep -v ^$ | sort | uniq | wc -l)
	if [ -z "$(echo $(($phycore*2)) | grep $nproc)" ]; then
		echo "Does not look like you have HTi/AMT Enabled"
		if [ -z "$( dmidecode -t processor | grep HTT)" ]; then
			echo "HyperThreading/AMT isn't available on this machine"
			ret="0"
		else
			echo "This server is HyperThreading capable, however, it is disabled"
			ret="0"
		fi
	else
		echo "HyperThreading/AMT is enabled; disabled is recommended"
		ret="254"
	fi
fi
exit $ret
