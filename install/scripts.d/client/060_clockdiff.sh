#!/bin/bash

DESCRIPTION="Verify timesync"
# script type is single, parallel, or sequential
SCRIPT_TYPE="single"

ret="0"

# Verify we have clockdiff
which clockdiff &> /dev/null
if [ $? -eq 1 ]; then
	if [[ $ID_LIKE == *debian* ]]; then
		PACKAGE="iputils-clockdiff"
	elif [[ $ID_LIKE == *rhel* ]]; then
		PACKAGE="iputils"
	fi
	echo "clockdiff not found." 
	if [ "$FIX" == "True" ]; then
		echo "Fix requested. Installing clockdiff"
		if [[ $ID_LIKE == *debian* ]]; then
			sudo apt-get update
			sudo apt-get -y install iputils-clockdiff
		elif [[ $ID_LIKE == *rhel* ]]; then
			sudo yum -y install iputils
		fi
		which clockdiff &> /dev/null
		if [ $? -eq 1 ]; then
			echo "Fix failed - clockdiff still not found"
			echo "Please install $PACKAGE"
			exit "1"
		fi
	else
		echo "Please install $PACKAGE or use --fix option"
		exit "1" #  FAIL
	fi
fi

echo
HOSTNAME= $(hostname)
RESULT=`clockdiff $CLUSTERIP`
DIFF=`echo $RESULT | awk '{ print $2 + $3 }'`
if [ $DIFF -lt 0 ]; then let DIFF="(( 0 - $DIFF ))"; fi
if [ $DIFF -gt 50 ]; then # up to 10ms is allowed
		echo "    FAIL: Host $HOSTNAME is not in timesync: time diff is $DIFF ms"
		ret="1"
else
		echo "        OK: Host $HOSTNAME timesync ok; diff is $DIFF"
fi

exit $ret
