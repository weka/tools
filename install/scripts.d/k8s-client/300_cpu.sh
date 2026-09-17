#!/bin/bash

DESCRIPTION="Check same cpu"
# just make sure all the servers are the same
SCRIPT_TYPE="parallel-compare-backends"

MODEL=$(lscpu | grep "^Model name:" | cut -d: -f2)
echo $MODEL

exit "0"


