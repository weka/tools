#!/bin/bash

DESCRIPTION="Verify bond and member MTUs match for any bonds"
SCRIPT_TYPE="parallel"

rc=0

for bonding_dir in /sys/class/net/*/bonding; do
	[ -d "$bonding_dir" ] || continue
	bond=$(basename "$(dirname "$bonding_dir")")
	bond_mtu=$(cat /sys/class/net/"$bond"/mtu)
	# "slaves" is the kernel's sysfs name for the bond member list
	members=$(cat "$bonding_dir"/slaves)

	for member in $members; do
		member_mtu=$(cat /sys/class/net/"$member"/mtu)
		if [ "$member_mtu" -ne "$bond_mtu" ]; then
			echo "FAIL: $member MTU ($member_mtu) does not match bond $bond's MTU ($bond_mtu)"
			rc=1
		fi
	done
done

if [ "$rc" -eq 0 ]; then
  echo "All tests passed."
fi
exit "$rc"
