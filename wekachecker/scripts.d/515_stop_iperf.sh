#!/bin/bash


DESCRIPTION="Stop all iperf servers"
SCRIPT_TYPE="parallel"

# Put your stuff here
sudo pkill iperf	# make sure it's not already running
#(iperf -s &> /dev/null) &
write_log "iperf servers stopped"

exit 0
