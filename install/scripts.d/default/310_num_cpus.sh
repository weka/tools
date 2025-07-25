#!/bin/bash

DESCRIPTION="Check number of cores"
# just make sure all the servers are the same
SCRIPT_TYPE="parallel-compare-backends"

lscpu | grep "^CPU(s):" | cut -d: -f2

exit "0"


