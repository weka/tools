#!/bin/bash

DESCRIPTION="Check NVMe's the same"
SCRIPT_TYPE="parallel-compare-backends"

lsblk | grep ^nvme | sort

exit 0