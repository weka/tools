#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for now-redundant overrides"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

declare -A REDUNDANT_OVERRIDE_LIST

# 2024-05-17: Copy / paste fom https://www.notion.so/wekaio/Active-.......-Overrides-7bd4a83d55a24ad29f109fb31e37ec7a
#REDUNDANT_OVERRIDE_LIST["value"]                                   = "redundant_from_version" # i.e. if at this version or later, the override is unnecessary
REDUNDANT_OVERRIDE_LIST["allow_dirty_up_to_unjustified_down_count"]="4.2.7"  # Cannot space-separate these to align columns :(
REDUNDANT_OVERRIDE_LIST["raid_journal_hound_bytes_per_sec"]="4.2.0"
REDUNDANT_OVERRIDE_LIST["rdma_force_disable_write"]="4.2.6"
REDUNDANT_OVERRIDE_LIST["rdma_readbinding_expiration_timeout_secs"]="4.0"
REDUNDANT_OVERRIDE_LIST["stripe_data_max_verification_blocks"]="4.2.6"

# Use core-util's sort -V to determine if version $1 is <= version $2                                                                                                                                                 
verlte() {
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}
verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
  echo "ERROR: Not able to run weka commands"
  exit 254
elif [[ $? -eq 127 ]]; then
  echo "WEKA not found"
  exit 254
elif [[ $? -eq 41 ]]; then
  echo "Unable to login into Weka cluster."
  exit 254
fi

CURRENT_WEKA_VERSION=$(weka version current)

# Iterates over each cluster leader container / mgmt IP combination
while read CURRENT_OVERRIDE; do
    # skip checking this override as it hasn't ever been marked redundant
    if [[ ! -n "${REDUNDANT_OVERRIDE_LIST[${CURRENT_OVERRIDE}]}" ]] ; then
        continue
    fi
    REDUNDANT_FROM_VERSION=${REDUNDANT_OVERRIDE_LIST[${CURRENT_OVERRIDE}]}
    if verlte ${REDUNDANT_FROM_VERSION} ${CURRENT_WEKA_VERSION} ; then
        echo "Override ${CURRENT_OVERRIDE} is no longer necessary as of v${REDUNDANT_FROM_VERSION}"
        RETURN_CODE=254
    fi
done < <(weka debug override list --output key --no-header)

if [[ $RETURN_CODE -eq 0 ]]; then
  echo "No redundant overrides detected."

fi

exit ${RETURN_CODE}
