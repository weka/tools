#!/bin/bash
# Test to check on errors on all backend NICs using ethtool -S <device_name> which are up
#
# Global settings
res="0"

function barline () {
## barline
echo "================================================================="
}

function testname () {
## testname

echo "Test name: Looking for errors on network ports"
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

# Looking for ethtool to to scan for port errors
which ethtool 1> /dev/null 2> /dev/null 
if [ $? -eq 1 ]; then
	echo "Ethtool not found"
	exit 1
fi

for f in /sys/class/net/*; do
	dev=$(basename $f)
	driver=$(readlink $f/device/driver/module)
	if [ $driver ]; then
		driver=$(basename $driver)
	fi
	addr=$(cat $f/address)
	operstate=$(cat $f/operstate)
	if [ "$operstate" == "up" ]; then
		echo "Looking at device name: $dev for errors"
		ethtool -S $dev|grep -i "_err" | grep ": [1-9]"
		if [ $? -ne 1 ]; then
			echo "Some errors found on $dev device below:"
			ethtool -S $dev | grep -i "_err" | grep ": [^0]"
			res="1"
		else
			echo "No errors found for $dev device name"
		fi
	fi
	#printf "%10s [%s]: %10s (%s)\n" "$dev" "$addr" "$driver" "$operstate"
done
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


