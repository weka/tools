#!/bin/bash

DESCRIPTION="Check netmasks the same"
SCRIPT_TYPE="parallel-compare-backends"

ip -o a | awk '{ print $4 }' | cut -d/ -f2

exit 0