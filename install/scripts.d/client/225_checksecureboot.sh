#!/bin/bash

DESCRIPTION="Check Secure Boot disabled"
SCRIPT_TYPE="parallel"

# BIOS systems
if ! [ -d /sys/firmware/efi/ ]; then
	echo 'Not UEFI system, Secure Boot disabled/not possible'
	exit 0
fi

if ! sb_state=$(mokutil --sb-state); then
	echo 'mokutil not found, unable to determine Secure Boot status'
	exit 254
fi

if [[ $sb_state = SecureBoot' 'disabled* ]]; then
	echo 'Secure Boot disabled'
	exit 0
elif [[ $sb_state = SecureBoot' 'enabled* ]]; then
	echo 'Secure Boot enabled; disable in the BIOS/UEFI interface'
	exit 254
else
	echo 'Unable to determine Secure Boot status'
	exit 254
fi
