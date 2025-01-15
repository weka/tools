#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for duplicate ARP entries"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2024-08-19

# It has been observed that incorrect IP to MAC mappings can occur,
# in Weka HA configurations, due to various upstream ARP control 
# mechanisms.

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    exit 254
elif [[ $? -eq 127 ]]; then
    echo "WEKA not found"
    exit 254
elif [[ $? -eq 41 ]]; then
    echo "Unable to login into Weka cluster."
    exit 254
fi

for MGMT_IP in $(weka cluster container net -o ips --no-header | tr ',' '\n' | tr -d " " | sort -u); do
    if [[ $(ip -br neigh | grep ${MGMT_IP} | awk '{print $3}' | sort -u | wc -l) -gt 1 ]]; then
        echo "WARN: Duplicate arp entry found for IP ${MGMT_IP}"
        echo "Recommended Resolution: check for IP clashes, and that there is a 1:1 mapping for IP:MACs"
        RETURN_CODE=254
    fi
done


if [[ ${RETURN_CODE} -eq 0 ]] ; then
    echo "No duplicate arp entries"
fi

exit $RETURN_CODE
