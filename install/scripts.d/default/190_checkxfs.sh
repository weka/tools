#!/bin/bash

DESCRIPTION="Check for XFS FS type installed"
SCRIPT_TYPE="parallel"

which mkfs.xfs &> /dev/null
if [ $? == 1 ]; then
    echo "ERROR: XFS not installed. XFS is required for WEKA installation.  Please install XFS"
    exit 255
else
	echo "XFS installed"
	ret="0"
fi

exit $ret
