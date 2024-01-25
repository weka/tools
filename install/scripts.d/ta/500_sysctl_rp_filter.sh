#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that the setting rp_filter is set to either 0 or 2"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

for INTERFACE_NAME in $(ip --json addr | jq -cr '.[]|select(.link_type!="loopback")|.ifname') ; do
    RP_FILTER_VALUE=$(sysctl -n net.ipv4.conf.${INTERFACE_NAME}.rp_filter)
    if [[ "${RP_FILTER_VALUE}" != "0" && "${RP_FILTER_VALUE}" != "2" ]]; then
        RETURN_CODE="254"
        echo "The value for net.ipv4.conf.${INTERFACE_NAME}.rp_filter is set to ${RP_FILTER_VALUE}"
        echo "This can disrupt floating IP addresses for protocols"
    fi
done

exit ${RETURN_CODE}
