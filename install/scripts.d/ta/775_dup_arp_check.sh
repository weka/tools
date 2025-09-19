#!/bin/bash

set -ue  # Exit on unset variables or errors

DESCRIPTION="Check for duplicate ARP entries"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2025-08-14

# Check if we can run weka commands
weka status &> /dev/null
RC=$?
if [[ $RC -eq 127 ]]; then
    echo "WEKA not found"
    exit 254
elif [[ $RC -eq 41 ]]; then
    echo "Unable to login into Weka cluster."
    exit 254
elif [[ $RC -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    exit 254
fi

 # Process each management IP
for MGMT_IP in $(weka cluster container -b -o ips --no-header | tr ',' '\n' | tr -d ' ' | sort -u); do
    NEIGH_LINE=$(ip neigh | grep -w "$MGMT_IP" || true)

    if echo "$NEIGH_LINE" | awk '{print $NF}' | grep -q -e FAILED -e INCOMPLETE; then
        echo "WARN: Failed/incomplete ARP entry for IP $MGMT_IP"
        echo "Recommended Resolution: verify switch configuration is not blocking or throttling ARP traffic"
        RETURN_CODE=254
    elif [[ $(echo "$NEIGH_LINE" | grep -v STALE | awk '{print $5}' | sort -u | wc -l) -gt 1 ]]; then
        echo "WARN: Duplicate ARP entry found for IP $MGMT_IP"
        echo "Recommended Resolution: check for IP clashes, and ensure a 1:1 mapping for IP:MACs"

        RETURN_CODE=254
    fi
done

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "No duplicate ARP entries"
fi

exit $RETURN_CODE
