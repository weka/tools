#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for custom CA TLS certificates"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="KB 1179"
RETURN_CODE=0

WEKA_VERSION=$(weka version current)

grep -q SSL_CERT_FILE /opt/weka/dist/release/${WEKA_VERSION}.spec 2>/dev/null

if [[ $? -eq 0 ]] ; then 
        echo "This version of weka appears to use custom CA certificates. Care will be needed for upgrading"
        echo "Recommended resolution: remove custom CA specification, and upgrade to a more recent"
        echo "version that natively supports additional CA bundles"
        RETURN_CODE=254
fi
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No custom CA certificates found"
fi
exit ${RETURN_CODE}
