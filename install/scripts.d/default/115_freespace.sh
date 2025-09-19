#!/bin/bash

DESCRIPTION="Check /opt/weka for sufficient capacity"
SCRIPT_TYPE="parallel"

# Checking if installation folder has enough free space for Weka.IO install - general requirement is 26Gb and additional 10Gb per CPU core

# for clients.. this can be as many as 8 cores (usually).   Typical is more like 4 cores.

OPT_WEKA="no"

if [ ! -d "/opt/weka" ]
then
	echo "/opt/weka does not exist.  /opt/weka should be a partition.  See docs.weka.io for details"
	ret="1"
	exit $ret
fi
# MOUNTED_ON=`df -h /opt/weka | tail -1 | awk '{print $6}'`

df -h /opt/weka | tail -1 | awk '{print $6}' | grep /opt &> /dev/null
if [ $? -eq 1 ]; then
        # No locally mounted /opt/dir to separate partition, which means opt is on /
	# Total No-No!
	OPT_WEKA="no"
else
        # There is locally mounted /opt/dir to separate partition, which means weka should be in /opt
	OPT_WEKA="yes"
fi

# Using `--block-size` always round upwards to nearest integer, so get MiB and
# convert to GiB and to 1 decimal place
local_free_space=$(df --block-size M --output=avail /opt/weka | awk '!/Avail/ { gsub("M", ""); gsub(" ", ""); print ($0 / 1024)}')

num_of_cpus=$(lscpu | awk '/^CPU\(s):/ { print $2 }')
num_of_sockets=$(lscpu | awk '/^Socket\(s)/ { print $2 }')
num_of_threads=$(lscpu | awk -F ':' '/^Thread\(s) per core:/ { gsub(" ", ""); print $2 }')
num_of_cores=`echo $(($num_of_cpus/$num_of_threads/$num_of_sockets))`

if [ "$num_of_cores" -le "19" ]; then
	space_needed=`echo $((($num_of_cores*10)+26))`
else
	space_needed=`echo $(((19*10)+26))`
fi

enough_space=$(awk "BEGIN { if ($local_free_space >= $space_needed) print \"y\" }")
if [ "$enough_space" = 'y' ]; then
	echo "There is enough space to run Weka.IO on this node"
	ret="0"
else
	echo "/opt/weka has only "$local_free_space"GiB free, but at least "$space_needed"GiB is recommended for $num_of_cores cores"
	ret="254"
fi

if [ "$OPT_WEKA" != "yes" ]; then
	echo "/opt/weka is not in a partition.  Please create a dedicated /opt/weka partition"
	echo "Note: You may NOT just symlink /opt/weka to another partition."
	ret="254"
fi

exit $ret
