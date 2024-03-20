#!/bin/bash

DESCRIPTION="Check if NUMA is set to NPS4"
SCRIPT_TYPE="parallel"

nps_value=$(lscpu | awk '/^NUMA node\(s):/ { print $3 }')

if [ "$nps_value" -eq "4" ]; then
    echo "NUMA is set to NPS4 on $HOSTNAME"
    ret="0"
else
    echo "NUMA is not set to NPS4 on $HOSTNAME (current value $nps_value)"
    ret="1"
fi

exit $ret
