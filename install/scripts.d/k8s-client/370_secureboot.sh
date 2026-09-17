#!/bin/bash

DESCRIPTION="Check Secure Boot same"
SCRIPT_TYPE="parallel-compare-backends"

# BIOS systems
if ! [ -d /sys/firmware/efi/ ]; then
	echo 'Not UEFI system, Secure Boot disabled/not possible'
	exit 0
fi

mokutil --sb-state

exit 0