#!/bin/bash

DESCRIPTION="Check for rpcbind enabled"
SCRIPT_TYPE="parallel"


systemctl status rpcbind &> /dev/null
if [ $? != 0 ]; then
    echo "error: rpcbind not running on `hostname`"
    exit 1
fi
echo "rpcbind is running"
exit 0
