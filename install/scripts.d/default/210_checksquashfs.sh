#!/bin/bash

DESCRIPTION="Check for squashfs enabled"
SCRIPT_TYPE="parallel"


grep squashfs /etc/modprobe.d/* &> /dev/null
if [ $? == 0 ]; then
    echo "ERROR: squashfs is disabled on `hostname`.  squashfs support is required for WEKA."
    exit 1
fi

exit 0
