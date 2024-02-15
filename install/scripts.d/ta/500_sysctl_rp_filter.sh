#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that the setting rp_filter is set to either 0 or 2"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

for INTERFACE_NAME in $(ip --json addr | python3 -c 'import sys, json; data = json.load(sys.stdin) ; print(" ".join([a["ifname"] for a in data if "loopback" not in a.get("link_type")]));') ; do
    RP_FILTER_VALUE=$(sysctl -n net.ipv4.conf.${INTERFACE_NAME}.rp_filter)
    if [[ "${RP_FILTER_VALUE}" != "0" && "${RP_FILTER_VALUE}" != "2" ]]; then
        RETURN_CODE="254"
        echo "The value for net.ipv4.conf.${INTERFACE_NAME}.rp_filter is set to ${RP_FILTER_VALUE}"
        echo "This can disrupt floating IP addresses for protocols"
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "The value for net.ipv4.conf.${INTERFACE_NAME}.rp_filter is set to either 0 or 2"
fi
exit ${RETURN_CODE}
