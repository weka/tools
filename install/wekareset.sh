#!/usr/bin/env bash 

#
# Remove WekaIO configuration from a group of hosts and baseline to STEM mode (leaving WekaIO software in tact)
#
# Written by: Vince Fleming, vince@weka.io
#

echo 'wekareset.sh is now deprecated; please see `wekadestroy --help` instead'
sleep 5

if [ $# -lt 1 ]; then
	echo "Usage: $0 <hosts>..."
	echo "where <hosts> is a space separated list of hosts to reset."
	echo "this command resets the Weka software to STEM mode for all hosts listed on the command line"
	exit
fi

echo -n "Are you SURE you want to reset these hosts? (yn): "
read ANS
if [ "$ANS" != "y" ]; then
	echo "Oh, thank goodness!"
	exit
fi

echo "Stopping IO on the cluster..."
sudo weka cluster stop-io

#
# clean 'em up!
#
NUM_HOSTS=0
for HOST in $*; do
	echo "Resetting $HOST..."
	let NUM_HOSTS=$NUM_HOSTS+1

	# check if weka is already installed on this HOST
	ssh $HOST which weka > /dev/null 2>&1
	if [ $? -ne 0 ]; then
		echo "	Weka is not installed on host $HOST!"
	else
		(
		# unmount any wekafs's   - could use to make it fancier just in case some are mounted on other wekafs'
		echo "  Unmounting wekafs' on $HOST"
		for i in `ssh $HOST mount | grep wekafs | cut -f3 "-d "`; do
			ssh $HOST sudo umount $i
		done
		
		# stop weka on the host
		echo "	Stopping Weka on $HOST"
		ssh $HOST sudo weka local stop #> /dev/null 2>&1
		if [ $? -ne 0 ]; then
			echo "	Unable to stop Weka on host $HOST"
		fi

		# reset weka
		echo "	Resetting Weka on $HOST"
		ssh $HOST sudo weka local reset-data -f #> /dev/null 2>&1
		if [ $? -ne 0 ]; then
			echo "	Unable to reset Weka on host $HOST"
		fi
		
		# restart weka on the host
		echo "	Starting Weka on $HOST"
		ssh $HOST sudo weka local start #> /dev/null 2>&1
		if [ $? -ne 0 ]; then
			echo "	Unable to start Weka on host $HOST"
		fi
		) &

	fi

done 


sleep 5
echo "Waiting for resets to complete..."
wait
echo "All reset processes have completed."
