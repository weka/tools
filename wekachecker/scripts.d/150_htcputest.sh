#!/bin/bash

DESCRIPTION="Check if HT is enabled"
SCRIPT_TYPE="parallel"

# Checking if CPU has HyperThreading available and running or disabled - test will always return true
which dmidecode &> /dev/null
if [ $? -eq 1 ]; then
	write_log "Dmidecode tool wasn't found, could not test HyperThreading properly"
	ret="0"
else
	nproc=$(grep -i "processor" /proc/cpuinfo | sort -u | wc -l)
	phycore=$(cat /proc/cpuinfo | egrep "core id|physical id" | tr -d "\n" | sed s/physical/\\nphysical/g | grep -v ^$ | sort | uniq | wc -l)
	if [ -z "$(echo $(($phycore*2)) | grep $nproc)" ]; then
		write_log "Does not look like you have HT Enabled"
		if [ -z "$( dmidecode -t processor | grep HTT)" ]; then
			write_log "HyperThreading isn't available on this machine"
			ret="0"
		else
			write_log "This server is HyperThreading capable, however, it is disabled, it is recommended to enable HyperThreading in the BIOS"
			ret="0"
		fi
	else
		write_log "HyperThreading is working and enabled"
		ret="0"
	fi
fi
exit $ret
