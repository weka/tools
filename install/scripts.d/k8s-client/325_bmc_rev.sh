#!/bin/bash

DESCRIPTION="Check BMC revision"
# just make sure all the servers are the same
SCRIPT_TYPE="parallel-compare-backends"

ipmitool mc info | grep "^Firmware Revision"

exit "0"


