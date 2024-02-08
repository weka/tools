#!/bin/bash

DESCRIPTION="Checking if Numa balancing is enabled"
SCRIPT_TYPE="parallel"

# Put your stuff here
if [ ! -e /proc/sys/kernel/numa_balancing ]; then
	echo "Could not find numa_balancing kernel entry in proc..."
	ret="1"
	return
else
	ret="0"
fi
numa_set=`cat /proc/sys/kernel/numa_balancing`
if [ "$numa_set" -eq "1" ]; then
	echo "Numa balancing is enabled in the current running kernel configuration."
	echo "    It is generally recommended to disable this setting by entering the following command:"
	echo "        echo 0 > /proc/sys/kernel/numa_balancing && echo 'kernel.numa_balancing=0' >> /etc/sysctl.conf"
	ret="254"

	# Fix it?
	if [ "$FIX" == "True" ]; then
		sudo bash -c "echo 0 > /proc/sys/kernel/numa_balancing"
		sudo bash -c "echo 'kernel.numa_balancing=0' >> /etc/sysctl.conf"
		echo "NUMA Balancing disabled."
		ret="254"
	fi
else
	echo "Numa balancing is disabled"
	ret="0"
fi

exit $ret
