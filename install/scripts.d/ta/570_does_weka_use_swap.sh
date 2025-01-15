#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if Weka processes are using swap"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="SFDC-12738"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0


for WEKAPID in $(ps -eo pid,comm | grep weka_init | awk '{print $1}') ; do
    # Enter the namespace of the weka_init process, drop the mount namespace, then mount a new proc
    # so we can check every process in the container for swap usage.
    NUM_PROCS_USING_SWAP=$(nsenter -a -t ${WEKAPID} unshare -m sh -c 'mount -t proc proc /proc ; grep -e "^VmSwap:\s*[^0]\ kB" /proc/*/status | wc -l')
    if [[ ${NUM_PROCS_USING_SWAP} -gt "0" ]] ; then
        echo "There are Weka processes using swap - this is likely to be"
        echo "detrimental to performance"
        echo "Recommended Resolutions:"
        echo " . Add more RAM if the host is truly constrained"
        echo " . Review if the host has not correctly released RAM"
        echo " . Reduce the amount of RAM allocated to WEKA (a last resort)"
        RETURN_CODE="254"
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "No Weka processes found using swap"
fi

exit ${RETURN_CODE}
