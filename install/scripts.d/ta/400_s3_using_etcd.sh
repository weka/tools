#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if still using etcd on S3 cluster"
SCRIPT_TYPE="single"
JIRA_REFERENCE="Migrating-S3-Clusters-from-Using-ETCD-to-KWAS-c783f71cc15f4c87a95df0ea2d97171a"
WTA_REFERENCE="WTA08172023"
KB_REFERENCE="KB 1181"
RETURN_CODE=0
MIN_VERSION="4.0"
MAX_VERSION="4.2.0"

# Use core-util's sort -V to determine if version $1 is <= version $2
verlte() {
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}
verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

# check if we can run weka commands
weka status &> /dev/null
status=$?
if [[ $status -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    if [[ $status -eq 127 ]]; then
        echo "WEKA not found"
    elif [[ $status -eq 41 ]]; then
        echo "Unable to log into Weka cluster"
    fi
    exit 254 # WARN
fi

WEKA_VERSION=$(weka version current)

WEKA_S3_RUNNING=$(weka s3 cluster --json | grep active | grep true | wc -l)

if [ ${WEKA_S3_RUNNING} -ge 1 ] ; then 
    if verlte ${MIN_VERSION} ${WEKA_VERSION} && verlte ${WEKA_VERSION} ${MAX_VERSION} ; then
        WEKA_ETCD_HOSTS=$(weka s3 cluster --json | python3 -c 'import sys, json; data = json.load(sys.stdin); print(len(data["etcd_cluster_hosts"]))')
        if [ ${WEKA_ETCD_HOSTS} -gt 0 ] ; then
            echo "S3 cluster is running, and this version of Weka requires a configuration change."
            if [[ ! -z "${WTA_REFERENCE}" ]]; then
                echo "Refer to ${JIRA_REFERENCE}, discussed in ${WTA_REFERENCE}, SFDC ${KB_REFERENCE}"
            else
                echo "Refer to ${JIRA_REFERENCE}, SFDC ${KB_REFERENCE}"                                                                                                   
            fi
            echo "If you require the S3 service, please contact Customer Success indicating"
            echo " you need to move the S3 service from ETCD to KWAS, as indicated in KB 1181"
            RETURN_CODE=254
        fi
    fi
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "S3 cluster is good"
fi
exit ${RETURN_CODE}
