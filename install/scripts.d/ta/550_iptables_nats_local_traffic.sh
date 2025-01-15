#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if iptables NATs any local address ranges"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="SFDC-13063"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# check if we can run iptables
iptables -vL &> /dev/null
status=$?
if [[ $status -ne 0 ]]; then
    exit 0 # lack of iptables is probably enough an indication we are not nat'ing
fi

for IP_ADDRESS in $(hostname --all-ip-addresses) ; do
    iptables -L -n -t nat | grep -q ${IP_ADDRESS}
    if [[ $? -eq 0 ]] ; then
        echo "Warning: it is possible that traffic to or from local IP address ${IP_ADDRESS} will be subject to NAT"
        echo "This can cause intra-WEKA communication errors"
        echo "Recommended Resolution: Do not NAT WEKA traffic"
        RETURN_CODE="254"
    fi
done
for IP_ROUTE in $(ip -4 --json route list  | python3 -c 'import sys, json, collections; data = json.load(sys.stdin) ; print("\n".join([(r["dst"]) for r in data]))' | grep -v default) ; do
    iptables -L -n -t nat | grep -q ${IP_ROUTE}
    if [[ $? -eq 0 ]] ; then
        echo "Warning: it is possible that traffic to or from subnet ${IP_ROUTE} will be subject to NAT"
        echo "This can cause intra-WEKA communication errors"
        echo "Recommended Resolution: Do not NAT WEKA traffic"
        RETURN_CODE="254"
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No iptables re-writing local addresses witnessed"
fi

exit ${RETURN_CODE}
