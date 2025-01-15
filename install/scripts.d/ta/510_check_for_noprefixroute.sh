#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Look for no prefix route on any IP address"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

# check if the ip command supports --json
ip --json addr &> /dev/null
status=$?
if [[ $status -ne 0 ]]; then
    echo "ERROR: Not able to run ip --json addr command"
    if [[ $status -eq 127 ]]; then
        echo "ip command not found"
    fi
    exit 254 # WARN
fi

# look for addr_info["family"] == "inet" && addr_info["noprefixroute"]
NOPREFIXROUTE_COUNT=$(ip --json addr | python3 -c 'import sys, json; data = json.load(sys.stdin) ; print(len([addr for entry in data for addr in entry["addr_info"] if addr.get("family") == "inet" and addr.get("noprefixroute")]))')

if [[ "${NOPREFIXROUTE_COUNT}" != "0" ]]; then
    RETURN_CODE="254"
    echo "Certain IP addresses are configured with noprefixroute. This will inhibit the ability"
    echo "of certain cluster floating ips to accurately determine which link should be preferred"
    echo "The command \"ip -o -f inet route list match xxx.xxx.xxx.xxx/32 scope link\" needs to"
    echo "be able to return a device for each floating IP configured"
    echo "Recommended Resolution: remove the noprefixroute flag or otherwise ensure the"
    echo " ip route list command given above can resolve the link on which you wish the"
    echo " floating IP to be configured"
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No IP addresses found with noprefixroute"
fi
exit ${RETURN_CODE}
