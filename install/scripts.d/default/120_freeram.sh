#!/bin/bash

DESCRIPTION="Check available RAM"
SCRIPT_TYPE="parallel"

# Checking if OS has enough RAM for proper Weka.IO runtime - general requirement is 6.33G for each CPU core host if there is a cluster of 12 nodes
current_free_ram=`free -g | grep -i "mem" | awk {'print $3'}`
echo "Current amount of RAM that is free for Weka.IO on this node is: $current_free_ram"G""
ret="0"

exit $ret

# does this even make sense to check?   Can we even predict the amount of ram that will be needed?
