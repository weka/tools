#!/bin/bash

DESCRIPTION="IP Jumbo Frames test"
# script type is single, parallel, or sequential
SCRIPT_TYPE="single"


# Put your stuff here

let ERRORS=0
let WARN=0
#
# check ssh connectivity, if given hostnames/ips on command line
#
if [ $# -gt 0 ]; then
	for i in $*
	do
		# check for jumbo frames working correctly as well as basic connectivity.
		sudo ping -M do -c 2 -i 0.2 -s 4064  $i &> /dev/null
		if [ $? -eq 1 ]; then	# 1 == error exists
			echo $PINGOUT
			echo "WARNING: Host $i JUMBO FRAME ping error."
			let WARN=$WARN+1
			# jumbo frame ping failed, let's see if we can ping with normal mtu
			#sudo ping -c 10 -i 0.2 -q $i &> /dev/null
			#if [ $? -eq 1 ]; then
			#	echo "ERROR: Host $i general ping error."
			#	let ERRORS=$ERRORS+1
			#else
			#	echo "Host $i non-jumbo ping test passed."
			#fi
		else
			echo "Host $i JUMBO ping test passed."
		fi
	done
else
	echo "No hosts specified, skipping ssh connectivity test."
fi

#echo "There were $ERRORS failures"

#if [ $ERRORS -gt 0 ]; then
#	exit 255		# if we can't ping all the servers, we can't continue
#elif [ $WARN -gt 0 ]; then
if [ $WARN -gt 0 ]; then
	exit 254		# jumbo frames not enabled/working on all, so warn
fi
exit 0
