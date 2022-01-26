#!/bin/bash

DESCRIPTION="Verify timesync"
# script type is single, parallel, or sequential
SCRIPT_TYPE="single"

ret="0"

# Put your stuff here
which clockdiff &> /dev/null
if [ $? -eq 1 ]; then

	if [ "$DIST" == "ubuntu" ]; then
		PACKAGE="iputils_clockdiff"
	else
		PACKAGE="iputils"
	fi

	echo "clockdiff not found." 

	if [ "$FIX" == "True" ]; then
		echo "Fix requested. Installing clockdiff"
		if [ "$DIST" == "ubuntu" ]; then
			sudo apt-get install iputils-clockdiff
		else
			sudo yum -y install iputils
		fi
	else
		echo "Please install $PACKAGE or use --fix option"
		exit "254" #  WARN
	fi
fi

for i in $*
do
	DIFF=`clockdiff $i | awk '{ print $2 + $3 }'`
	if [ $DIFF -lt 0 ]; then let DIFF="(( 0 - $DIFF ))"; fi
	echo "Diff is $DIFF"
	if [ $DIFF -gt 10 ]; then # up to 10ms is allowed
		echo "Host $i is not in timesync:"
		clockdiff $i
		echo
		ret="1"
	else
		echo "Host $i timesync ok"
	fi
done


exit $ret
