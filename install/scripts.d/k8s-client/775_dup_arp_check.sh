#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for duplicate ARP entries"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2026-09-10
# k8s-client variant: does not use the weka CLI. If backend IPs/hostnames are
# given on the command line, they are checked for failed and duplicate ARP
# entries. Otherwise every IPv4 neighbour is checked for duplicates only, as a
# failed entry for an arbitrary neighbour is not necessarily a problem.

TARGET_IPS=""
CHECK_FAILED=0
if [[ $# -gt 0 ]]; then
    CHECK_FAILED=1
    for HOST in "$@"; do
        DEST_IP=$(getent ahostsv4 "$HOST" 2>/dev/null | awk '{print $1; exit}')
        if [[ -n "$DEST_IP" ]]; then
            TARGET_IPS+="$DEST_IP "
        else
            echo "WARN: Unable to resolve $HOST, skipping"
        fi
    done
else
    TARGET_IPS=$(ip -4 neigh | awk '{print $1}' | sort -u | paste -s -d ' ')
fi

for TARGET_IP in ${TARGET_IPS}; do
    NEIGH_LINES=$(ip -4 neigh | grep -w "^${TARGET_IP}" || true)
    if [[ -z "${NEIGH_LINES}" ]]; then
        continue
    fi
    if [[ ${CHECK_FAILED} -eq 1 ]] && echo "${NEIGH_LINES}" | awk '{print $NF}' | grep -q -e FAILED -e INCOMPLETE; then
        echo "WARN: Failed/incomplete ARP entry for IP ${TARGET_IP}"
        echo "Recommended Resolution: verify switch configuration is not blocking or throttling ARP traffic"
        RETURN_CODE=254
    elif [[ $(echo "${NEIGH_LINES}" | grep -v STALE | grep lladdr | awk '{for(i=1;i<=NF;i++) if($i=="lladdr") print $(i+1)}' | sort -u | wc -l) -gt 1 ]]; then
        echo "WARN: Duplicate ARP entry found for IP ${TARGET_IP} (more than one MAC address)"
        echo "Recommended Resolution: check for IP clashes, and ensure a 1:1 mapping for IP:MACs"
        RETURN_CODE=254
    fi
done

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "No duplicate ARP entries"
fi

exit $RETURN_CODE
