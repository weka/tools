#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Ensure /opt/weka is not a symlink"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC #13789"
RETURN_CODE=0

main() {
    if [[ -L /opt/weka ]] ; then
        echo "/opt/weka is a symlink. This is not supported and"
        echo "is very unlikely to work due to chroot-style container behaviour"
        echo "Recommended Resolution: Do not install Weka in a symlink"
        echo "Resolving this can involve a rolling deactivation and re-installation"
        echo "of Weka, depending on how and why this was done"
        RETURN_CODE=254
    else
        echo "/opt/weka is not a symlink. This is ok"
        RETURN_CODE=0
    fi
    exit ${RETURN_CODE}
}

main "$@"
