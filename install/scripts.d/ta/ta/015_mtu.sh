#!/bin/bash

DESCRIPTION="Verify master and slave MTUs match for any bonds"
SCRIPT_TYPE="parallel"

rc=0
masters=$(cat /sys/class/net/bonding_masters)

for master in $masters; do
	master_mtu=$(cat /sys/class/net/"$master"/mtu)
	slaves=$(cat /sys/class/net/"$master"/bonding/slaves)

	for slave in $slaves; do
		slave_mtu=$(cat /sys/class/net/"$slave"/mtu)
		if [ "$slave_mtu" -ne "$master_mtu" ]; then
			echo "FAIL: $slave MTU ($slave_mtu) does not match master $master's MTU ($master_mtu)"
			rc=1
		fi
	done
done

if [ "$rc" -eq 0 ]; then
  echo "All tests passed."
fi
exit "$rc"
