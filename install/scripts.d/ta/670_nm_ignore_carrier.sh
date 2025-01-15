#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check to see if NetworkManager has ignore-carrier"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-392845"
WTA_REFERENCE=""
KB_REFERENCE="KB 1214"
RETURN_CODE=0

# Ref: https://access.redhat.com/solutions/894763

if nmcli -v &> /dev/null; then
    if nmcli dev status | grep connected &> /dev/null; then
        IGNORE_CARRIER=$(NetworkManager --print-config | grep -E -v ^# | grep ignore-carrier | cut -d '=' -f 2)
        if [[ -z $IGNORE_CARRIER ]]; then
            RETURN_CODE=254
            echo "NetworkManager ignore-carrier is not set. Recommended value is ignore-carrier=*"
        elif [[ "$IGNORE_CARRIER" != "*" ]]; then
            RETURN_CODE=254
            echo "NetworkManager ignore-carrier is set to ${IGNORE_CARRIER}, but recommended value is ignore-carrier=*"
            echo "Recommended Resolution: set ignore-carrier=* in NetworkManager, perhaps with the following commands"
            echo "  echo -e '[main]\\nignore-carrier=*' > /etc/NetworkManager/conf.d/99-carrier.conf "
            echo "  systemctl restart NetworkManager "
        else
            echo "NetworkManager ignore-carrier=* exists."
        fi
    else
        echo "NetworkManager not in use."
    fi
else
    echo "NetworkManager not in use."
fi

exit ${RETURN_CODE}
