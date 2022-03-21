#!/usr/bin/env bash 

#
# Deploy WekaIO to a group of hosts (does not configure)
#
# Written by: Vince Fleming, vince@weka.io
#

#set -x

if [ $# -lt 2 ]; then
	echo "Usage: $0 <weka_tarfile> <hosts>..."
	echo "where <weka_tarfile> is the name of the WekaIO release tar file and"
	echo "where <hosts> is a space separated list of hosts to deploy to."
	exit
fi

echo -n "Have you run the wekachecker script? (yn): "
read ANS
if [ "$ANS" != "y" ]; then
	echo "Please run wekachecker before attempting to run this script."
	exit
fi

#
# Copy and unpack the tar file to each host; wait to install later, so we don't fail halfway through and have to reset the config because of an ssh error
#
TARFILE=$1
shift
NUM_HOSTS=0
WEKA_INSTALLED="False"
for HOST in $*; do
	echo "Preparing $HOST"
	let NUM_HOSTS=$NUM_HOSTS+1

	# check if weka is already installed on this host
	ssh $HOST which weka > /dev/null 2>&1
	if [ $? -eq 0 ]; then
		echo "Weka is already installed on host $HOST!"
		WEKA_INSTALLED="True"
	else
		# check if we've copied it there already
		ssh $HOST ls $TARFILE > /dev/null 2>&1
		if [ $? -ne 0 ]; then
			echo "Copying tar file to host $HOST..."
			scp $TARFILE $HOST:~
			if [ $? -ne 0 ]; then
				echo "Error coping tar file to $HOST"
				exit
			fi
		fi

		# unpack it anyway - doesn't take long
		echo "Unpacking tar file on host $HOST..."
		ssh $HOST tar xvf `basename $TARFILE` > /dev/null 2>&1
		if [ $? -ne 0 ]; then
			echo "Error unpacking tar file on $HOST"
			exit
		fi
	fi

done 

if [ $WEKA_INSTALLED == "True" ]; then
	echo "Weka is already installed on at least one of the specified hosts."
	echo "Please remove Weka from all hosts and try again"
	exit
fi

echo "There are a total of $NUM_HOSTS hosts to be installed."

# go run the install.sh
WEKA_DIR=`basename ${TARFILE%.*}`
echo "Weka dir is $WEKA_DIR"
for HOST in $*; do
	echo "Installing Weka on $HOST"
	(
	ssh $HOST cd $WEKA_DIR \; sudo ./install.sh > /dev/null 2>&1
	if [ $? -ne 0 ]; then
		echo "Error installing Weka on $HOST"
		exit
	fi
	echo "Installation process on $HOST complete."
	) &
done 

sleep 5
echo "Waiting for installations to complete..."
wait
echo "All installation processes have completed."

# check that they're all running and in STEM mode
for HOST in $*; do
	echo -n "Checking Weka on $HOST: "
	ssh $HOST weka status | head -1
	
	if [ $? -ne 0 ]; then
		echo "Error installing Weka on $HOST"
		exit
	fi
done 


