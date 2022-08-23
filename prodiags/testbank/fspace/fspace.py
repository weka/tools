#!/bin/bash
    
# Globals
res="0"

function barline () {
## barline
echo "================================================================="
}

function testname () {
## testname
echo "Test name: Testing basic disk usage test"
which hostname 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
	echo "Hostname command not found"
else
	echo "Hostname: `hostname`"
	echo "IP address: `hostname -I`"
fi
}

function testrun () {
# Test run
barline
testname

min_space="1"

root_fspace=`df / | tail -1 | awk '{ printf "%5.0f\n", $4 /1024/1024 }' | sed 's/ //g'`
if [ "$root_fspace" -lt "$min_space" ]; then
	echo "Not enough free space on / partition"
	echo "Current free space on / is: `df / | tail -1 | awk '{ printf "%5.1f\n", $4 /1024/1024 }' | sed 's/ //g'`GB"
	res="1"
fi

optweka_fspace=`df /opt/weka | tail -1 | awk '{ printf "%5.0f\n", $4 /1024/1024 }' | sed 's/ //g'`
if [ "$root_fspace" -lt "$min_space" ]; then
	echo "Not enough free space on /opt/weka partition"
	echo "Current free space on /opt/weka is: `df /opt/weka | tail -1 | awk '{ printf "%5.1f\n", $4 /1024/1024 }' | sed 's/ //g'`GB"
	res="1"
fi

}

# MAIN
# If there is parameter after the script run command, output everything out

if [ "$1" ]; then
	testrun
	if [ "$res" -eq "1" ]; then
		exit 1
	fi
else
	rm /tmp/$(basename $0).log 1> /dev/null 2> /dev/null
	testrun > /tmp/$(basename $0).log
	if [ "$res" -ne "0" ]; then
		cat /tmp/$(basename $0).log
		rm /tmp/$(basename $0).log 1> /dev/null 2> /dev/null
		exit 1
	else
		rm /tmp/$(basename $0).log 1> /dev/null 2> /dev/null
		exit 0
	fi
fi
