#!/bin/bash

DESCRIPTION="Check same amount of ram"
# just make sure all the servers are the same
SCRIPT_TYPE="parallel-compare-backends"

#grep MemTotal /proc/meminfo
free -g | grep ^Mem: | awk '{ print $2 }'

exit "0"


