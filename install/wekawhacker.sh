#!/usr/bin/env bash 

#
# Remove WekaIO from a group of hosts
#
# Written by: Vince Fleming, vince@weka.io
#

echo 'wekawhacker.sh is now deprecated; please see `wekacleanup --help` instead'
sleep 5

if [ $# -lt 1 ]; then
	echo "Usage: $0 <hosts>..."
	echo "where <hosts> is a space separated list of hosts"
	exit
fi

echo -n "Are you SURE you want to whack these hosts? (yn): "
read ANS
if [ "$ANS" != "y" ]; then
	echo "Oh, thank goodness!"
	exit
fi

#
# clean 'em up!
#
NUM_HOSTS=0
for HOST in $*; do
	echo "Whacking $HOST..."
	let NUM_HOSTS=$NUM_HOSTS+1

	# check if weka is already installed on this HOST
	ssh $HOST which weka > /dev/null 2>&1
	if [ $? -ne 0 ]; then
		echo "	Weka is not installed on host $HOST!"
	else
		(
		# unmount any wekafs's
		echo "  Unmounting wekafs' on $HOST"
		for i in `ssh $HOST mount | grep wekafs | cut -f3 "-d "`; do
			ssh $HOST sudo umount $i
		done
		
		# stop weka on the host
		echo "	Stopping Weka on $HOST"
		ssh $HOST sudo weka local stop > /dev/null 2>&1
		if [ $? -ne 0 ]; then
			echo "	Unable to stop Weka on host $HOST"
		fi

		# uninstall weka
		echo "	Uninstalling Weka on $HOST"
		ssh $HOST sudo weka agent uninstall --force > /dev/null 2>&1
		if [ $? -ne 0 ]; then
			echo "	Unable to uninstall Weka on host $HOST"
		fi
		) &

	fi

done 


sleep 5
echo "Waiting for uninstalls to complete..."
wait
echo "All uninstallation processes have completed."

for HOST in $*; do

	# clean up anyway
	echo "	Cleaning up $HOST"
	ssh $HOST rm -rf /opt/weka/\* > /dev/null 2>&1
	if [ $? -ne 0 ]; then
		echo "	Error cleaning up $HOST"
		exit
	fi

done 
