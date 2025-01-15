#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check tcp connectivity to management ports of backends."
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2024-11-05

# Assumption / limitations
#  Must permit ICMP (ping)
#  Only performs TCP pings against the management ports (base_port + 0)

declare -A BACKEND_MGMT_PORTS
declare -A BACKEND_IPS

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

while read CONTAINER_ID; do
    curr_ips=()
    BACKEND_MGMT_PORTS[${CONTAINER_ID}]=$(weka cluster container ${CONTAINER_ID} -J | grep mgmt_port | grep -o "[0-9]\+")

    for IP in $(weka cluster container ${CONTAINER_ID} -o ips --no-header | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+\.[0-9]\+"); do
        curr_ips="${curr_ips} ${IP}"
    done

    BACKEND_IPS[${CONTAINER_ID}]=${curr_ips}
done < <(weka cluster container -b -o id --no-header)

# Perform the port checks
for CONTAINER_ID in ${!BACKEND_IPS[@]}; do
    curr_ips=${BACKEND_IPS[$CONTAINER_ID]}
    port=${BACKEND_MGMT_PORTS[$CONTAINER_ID]}

    for ip in ${curr_ips[@]}; do
        # If it does not respond to a ping, within 250ms,
        # assume the IP is not valid / reachable.
        if (ping -c 1 -q -W 250 $ip &>/dev/null); then
            if (! echo -n 2>/dev/null < /dev/tcp/$ip/$port); then
                echo "WARN: Unable to connect to $ip tcp/$port"
                echo "Recommended Resolution: There is likely something blocking network communication between"
                echo "this host and ${ip} tcp/${port}. Please review network connectivity and/or firewalls"
                echo "In particular DDOS-style protection on switches may prevent communication"
                RETURN_CODE=254
            fi

        else
            echo "WARN: Unable to ping $ip"
            RETURN_CODE=254
        fi
    done
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No backend management ports blocked."
fi

exit ${RETURN_CODE}
