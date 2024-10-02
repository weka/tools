#!/bin/bash

DESCRIPTION="Check if Hyperthreading (SMT) is disabled"
SCRIPT_TYPE="parallel"

RETURN_CODE=0
SMT_FILE="/sys/devices/system/cpu/smt/active"
if [[ ! -e "${SMT_FILE}" ]] ; then
    echo "File ${SMT_FILE} does not exist, assuming no hyperthreading"
    RETURN_CODE=0
    exit ${RETURN_CODE}
fi
    
SMT_ACTIVE=$(cat "${SMT_FILE}")
if [[ ${SMT_ACTIVE} -eq "0" ]] ; then
    echo "Hyperthreading/SMT is inactive, passing test"
    RETURN_CODE=0
else
    echo "Hyperthreading/SMT is active, which is not recommended"
    RETURN_CODE=254
fi
exit ${RETURN_CODE}
