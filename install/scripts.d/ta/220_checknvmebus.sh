#!/bin/bash

DESCRIPTION="Check for any NVMe devices on PCIe bus addresses >= 0x10000"
SCRIPT_TYPE="parallel"

nvme_buses=$(lspci | awk -F ':' '/Non-Volatile memory controller/ { print "0x"$1 }')

non_compliant_bus_ids=()

for bus_id in $nvme_buses; do
	if [[ $bus_id -ge 0x10000 ]]; then
		non_compliant_bus_ids+=("$bus_id")
	fi
done

if [ "${#non_compliant_bus_ids[@]}" -eq 0 ]; then
	echo 'There are no NVMe devices on bus IDs at or above 10000.'
	exit 0
else
	echo "Non-compliant PCIe bus addresses: ${non_compliant_bus_ids[*]}"
	echo 'See `lspci` for further details. These are incompatible with DPDK.'
	echo 'You may need to disable Intel VMD or exclude these devices from'
	echo 'VMD in the BIOS, or exclude these devices from your WEKA cluster.'
	exit 254
fi
