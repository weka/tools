#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Look for "
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

NOPREFIXROUTE_COUNT=$(ip --json addr | jq '[.[].addr_info[]|select((.family=="inet")and(.noprefixroute))]|length')

if [[ "${NOPREFIXROUTE_COUNT}" != "0" ]]; then
    RETURN_CODE="254"
    echo "Certain IP addresses are configured with noprefixroute. This will inhibit the ability"
    echo "of certain cluster floating ips to accurately determine which link should be preferred"
    echo "The command \"ip -o -f inet route list match xxx.xxx.xxx.xxx/32 scope link\" needs to"
    echo "Be able to return a device for each floating IP configured"
fi

exit ${RETURN_CODE}
