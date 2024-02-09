#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

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

WEKA_VERSION=$(weka version current)

WEKA_S3_RUNNING=$(weka s3 cluster --json | grep active | grep true | wc -l)

if [ ${WEKA_S3_RUNNING} -ge 1 ] ; then 
    if verlte ${MIN_VERSION} ${WEKA_VERSION} && verlte ${WEKA_VERSION} ${MAX_VERSION} ; then
        WEKA_ETCD_HOSTS=$(weka s3 cluster --json | jq ".etcd_cluster_hosts|length")
        if [ ${WEKA_ETCD_HOSTS} -gt 0 ] ; then
            echo "S3 cluster is running, and this version of Weka requires migration"
            if [[ ! -z "${WTA_REFERENCE}" ]]; then
                echo "to ${JIRA_REFERENCE}, discussed in ${WTA_REFERENCE}, SFDC ${KB_REFERENCE}"
            else
                echo "to ${JIRA_REFERENCE}, SFDC ${KB_REFERENCE}"                                                                                                   
            fi
            RETURN_CODE=254
        fi
    fi
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "S3 cluster is good"
fi

exit ${RETURN_CODE}
