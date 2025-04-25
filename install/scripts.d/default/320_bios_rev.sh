#!/bin/bash

DESCRIPTION="Check BIOS revision"
# just make sure all the servers are the same
SCRIPT_TYPE="parallel-compare-backends"

dmidecode -s bios-revision

exit "0"


