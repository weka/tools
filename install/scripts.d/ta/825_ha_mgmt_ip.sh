#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if each Weka container has a corresponding, valid, management IP"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

MIN_MGMT_IPS=""
MAX_MGMT_IPS=""

for WEKA_CONTAINER in $(weka local ps --output name --no-header | awk '/compute|drive|frontend/'); do
    IP_NOT_FOUND=()

    IPS_LINE=$(weka local resources -C "$WEKA_CONTAINER" --stable | awk '/Management IPs/ { $1="";$2=""; print $0 }' | sed 's/^ *//')
    IFS=',' read -ra IPS <<< "$IPS_LINE"

    for IP in "${IPS[@]}"; do
        CLEAN_IP=$(echo "$IP" | xargs)
        if ! ip -j -o addr show 2>/dev/null | grep -qw "$CLEAN_IP"; then
            IP_NOT_FOUND+=("$CLEAN_IP")
            RETURN_CODE=255
        fi
    done

    if [[ ${#IP_NOT_FOUND[@]} -gt 0 ]]; then
        echo "ERROR: container ${WEKA_CONTAINER} has ${#IPS[@]} management IPs assigned, but the following were not found: ${IP_NOT_FOUND[*]}."
        RETURN_CODE=255
    fi

    if [[ -z "$MIN_MGMT_IPS" ]]; then
        MIN_MGMT_IPS="${#IPS[@]}"
        MAX_MGMT_IPS="${#IPS[@]}"
    elif [[ ${#IPS[@]} -lt $MIN_MGMT_IPS ]]; then
        MIN_MGMT_IPS="$#IPS[@]"
    elif [[ ${#IPS[@]} -gt $MAX_MGMT_IPS ]]; then
        MAX_MGMT_IPS="${#IPS[@]}"
    fi
done

if [[ $MIN_MGMT_IPS -ne $MAX_MGMT_IPS ]]; then
    echo "ERROR: discrepancy in management IP count across containers (max="$MAX_MGMT_IPS", min="$MIN_MGMT_IPS")."
    RETURN_CODE=255
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All management IPs located"
else
    echo "Recommended Resolution: assign an appropriate set of management ips for each container."
    echo "Management IPs can be set by running the following commands:"
    echo "weka local resources -C <WEKA-CONTAINER> management-ips <IP1> <IP2>"
    echo "weka local resources -C <WEKA-CONTAINER> apply"
fi

exit ${RETURN_CODE}