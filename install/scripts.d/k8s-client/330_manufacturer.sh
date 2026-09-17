#!/bin/bash

DESCRIPTION="Check Manufacturer"
# just make sure all the servers are the same
SCRIPT_TYPE="parallel-compare-backends"

dmidecode -s system-manufacturer

exit "0"


