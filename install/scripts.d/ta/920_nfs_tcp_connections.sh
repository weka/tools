#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="NFS-W TCP socket usage"
JIRA_REFERENCE="WEKAPP-502848"
SCRIPT_TYPE="parallel"

# Maximum number of open NFS TCP sessions is 1024 - check if failover would take us beyond that limit too

# Check if we can run weka commands
weka status &> /dev/null
RC=$?

case ${RC} in
    254)
        echo "ERROR: Not able to run weka commands."
        exit 254
        ;;
    127)
        echo "WEKA not found."
        exit 254
        ;;
    41)
        echo "Unable to login to Weka cluster."
        exit 254
        ;;
esac

# Are we on a host w/ a Ganesha container?
if ! weka local status ganesha &> /dev/null; then
    echo "INFO: NFSW not running"
    exit 0
fi

# can we run ss?
ss >/dev/null 2>/dev/null
if [[ "$?" -ne "0" ]] ; then
    echo "INFO: cannot run ss"
    exit 0
fi

HARD_LIMIT=1024

LOCAL_CONNECTIONS=$(ss --no-header -t sport 2049 | wc -l)
if [[ -z "${LOCAL_CONNECTIONS}" ]]; then
    echo "INFO: 0 connections counted"
    exit 0
fi

NUMBER_OF_NFS_HOSTS=$(weka nfs interface-group -J | grep HostId | tr -d -c '[0-9\n]' | sort -n | uniq | wc -l)

PERCENT=$(awk -v used="${LOCAL_CONNECTIONS}" -v max="${HARD_LIMIT}" 'BEGIN { printf "%.0f", (used / max) * 100 }')

if [[ ${NUMBER_OF_NFS_HOSTS} -eq "1" ]] ; then
    echo "WARN: Only one NFS host configured - this represents a Single Point of Failure"
    exit 254
else
    PERCENT_IF_ONE_HOST_LOST=$(awk -v nfshosts=${NUMBER_OF_NFS_HOSTS} -v used="${LOCAL_CONNECTIONS}" -v max="${HARD_LIMIT}" 'BEGIN { printf "%.0f", (used / max) * 100 * (nfshosts / (nfshosts-1))}')
fi

if [[ "${PERCENT}" -ge 70 ]]; then
    echo "WARN: Number of NFS connections is above 70% of the hard limit"
    echo "This can severely hamper performance."
    echo "Recommended Resolution: add more NFS servers and distribute client load"
    exit 254
elif [[ "${PERCENT_IF_ONE_HOST_LOST}" -ge 70 ]]; then
    echo "WARN: Number of NFS connections is projected to rise above 70% of the hard limit if one NFS host were to be lost"
    echo "This can severely hamper performance."
    echo "Recommended Resolution: add more NFS servers and distribute client load"
    exit 254
else
    echo "INFO: NFS connections appears to be within sensible limits on this host"
fi
