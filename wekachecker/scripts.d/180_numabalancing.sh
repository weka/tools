#!/bin/bash

DESCRIPTION="Checking if Numa balancing is enabled"
SCRIPT_TYPE="parallel"

# Put your stuff here
if [ ! -e /proc/sys/kernel/numa_balancing ]; then
	write_log "Could not find numa_balancing kernel entry in proc..."
	ret="1"
	return
else
	ret="0"
fi
numa_set=`cat /proc/sys/kernel/numa_balancing`
if [ "$numa_set" -eq "1" ]; then
	write_log "Numa balancing is enabled in the current running kernel configuration, it is generally recommended to disable this setting by entering the following command"
	write_log "echo 0 > /proc/sys/kernel/numa_balancing && echo "kernel.numa_balancing=0" >> /etc/sysctl.conf"
	ret="254"

	# Fix it?
	if [ "$FIX" == "True" ]; then
		sudo bash -c "echo 0 > /proc/sys/kernel/numa_balancing"
		sudo bash -c "echo 'kernel.numa_balancing=0' >> /etc/sysctl.conf"
		write_log "NUMA Balancing disabled."
		ret="254"
	fi
else
	write_log "Numa balancing is disabled"
	ret="0"
fi

exit $ret
