#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if iptables NATs any local address ranges"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="SFDC-13063"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

if iptables -vL &> /dev/null; then
    for IP_ADDRESS in $(hostname --all-ip-addresses); do
        if iptables -L -n -t nat | grep -q ${IP_ADDRESS}; then
            echo "WARN: it is possible that traffic to or from local IP address ${IP_ADDRESS} will be subject to NAT."
            echo "This can cause intra-WEKA communication errors."
            echo "Recommended Resolution: Do not NAT WEKA traffic."
            RETURN_CODE="254"
        fi
    done
    for IP_ROUTE in $(ip -4 route | awk '$1!="default" {print $1}'); do
        if iptables -L -n -t nat | grep -q ${IP_ROUTE}; then
            echo "WARN: it is possible that traffic to or from subnet ${IP_ROUTE} will be subject to NAT."
            echo "This can cause intra-WEKA communication errors."
            echo "Recommended Resolution: Do not NAT WEKA traffic."
            RETURN_CODE="254"
        fi
    done
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No iptables re-writing local addresses witnessed."
fi

exit ${RETURN_CODE}