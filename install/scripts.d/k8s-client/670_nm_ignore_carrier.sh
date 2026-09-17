#!/bin/bash
DESCRIPTION="Check to see if NetworkManager has ignore-carrier"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-392845"
WTA_REFERENCE=""
KB_REFERENCE="KB 1214"
RETURN_CODE=0

if ! command -v nmcli &>/dev/null || ! systemctl is-active NetworkManager &>/dev/null; then
    echo "NetworkManager not in use."
    exit ${RETURN_CODE}
fi

IGNORE_CARRIER=$(NetworkManager --print-config | awk '!/^[[:space:]]*#/ && /^[[:space:]]*ignore-carrier[[:space:]]*=/ {split($0, a, "="); print a[2]; exit}')

if [[ -z "$IGNORE_CARRIER" ]]; then
    RETURN_CODE=254
    echo "NetworkManager ignore-carrier is not set. Recommended value is ignore-carrier=*"
elif [[ "$IGNORE_CARRIER" != "*" ]]; then
    RETURN_CODE=254
    echo "NetworkManager ignore-carrier is set to ${IGNORE_CARRIER}, but recommended value is ignore-carrier=*"
    echo "Recommended Resolution: set ignore-carrier=* in NetworkManager, perhaps with the following commands"
    echo "  echo -e '[main]\\nignore-carrier=*' > /etc/NetworkManager/conf.d/99-carrier.conf"
    echo "  systemctl restart NetworkManager"
else
    echo "NetworkManager ignore-carrier=* exists."
fi

exit ${RETURN_CODE}