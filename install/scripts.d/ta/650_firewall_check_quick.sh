#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check tcp connectivity to management ports of backends."
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2024-09-23

# Assumption / limitations
#  Queries weka local status for valid list of backend IPs
#  Only performs TCP pings against the management ports (base_port + 0)
#  Assumes weka local status output structure is static

declare -A BACKEND_IPS

curr_ip=""
curr_ips=()

# Determine what "base" ports each backend is using
while read line; do
    if [[ $line =~ ^"ip: "(.*) ]]; then
        curr_ip=${BASH_REMATCH[1]}
        curr_ips+=($curr_ip)
    elif [[ $line =~ ^"port: "(.*) ]]; then
        port=${BASH_REMATCH[1]}
        if [[ -z ${BACKEND_IPS[$curr_ip]+set} ]]; then
            BACKEND_IPS[$curr_ip]="$port:"
        elif [[ ! ${BACKEND_IPS[$curr_ip]} =~ "$port:" ]]; then # Only add if not there
            BACKEND_IPS[$ip]="${BACKEND_IPS[$ip]}$port:"
        fi
    elif [[ $line =~ ^"base_port: "(.*) ]]; then
        base_port=${BASH_REMATCH[1]}
        for ip in ${curr_ips[@]}; do
            if [[ ! ${BACKEND_IPS[$ip]} =~ "$base_port:" ]]; then # Only add if not there
                BACKEND_IPS[$ip]="${BACKEND_IPS[$ip]}$base_port:"
            fi
        done
        curr_ips=()
    fi
done < <(weka local status -J 2>/dev/null | grep -w -e "ip\":" -e "port\":" -e "base_port\":" | tr -d '",')


# Perform the port checks
for ip in ${!BACKEND_IPS[@]}; do
    # If it does not respond to a ping, within 250ms,
    # assume the IP is not valid / reachable.
    if (ping -c 1 -q -W 250 $ip &>/dev/null); then
        IFS=':' read -r -a ports <<< "${BACKEND_IPS[$ip]}"
        for port in ${ports[@]}; do
            if (! echo -n 2>/dev/null < /dev/tcp/$ip/$port); then
                echo "WARN: Unable to connect to $ip tcp/$port"
                RETURN_CODE=254
            fi
        done
    else
        echo "WARN: Unable to ping $ip"
        RETURN_CODE=254
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No backend management ports blocked."
fi

exit ${RETURN_CODE}