#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for multiple version-specific possible bugs"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="single"


#An array of strings (because bash can't do AoA). Each string is defined as:
# "min affected version;max affected version;WEKA Internal bugref;WEKA Internal Technical Advisory;Brief description"
# The minimum version is the first version that is susceptible to the bug (tested with >=).
# The maximum version is the final version that is susceptible (tested with <=).
# Internal bugref is e.g. a JIRA number e.g. WEKAPP-12345
# WTA is a TA number e.g WTA-20231010
# All values are optional; if there's no minimum version it will be assumed it's every version prior to max
# if there's no maximum it will be assumed it's every version subsequent to min.
declare -a WEKA_VERSION_TABLE

WEKA_VERSION_TABLE+=("     ;4.2.0;   WEKAPP-315823;WTA-08292023;KB 1180;NDU rolling update blocked by bucket start-up")
WEKA_VERSION_TABLE+=("4.2.0;4.2.0   ;WEKAPP-323045;            ;KB 1183;Check for possible Weka bucket count disparity")
WEKA_VERSION_TABLE+=("     ;4.2.1.21;WEKAPP-312395;            ;KB 1178;Potentially unroutable cluster management addresses")
WEKA_VERSION_TABLE+=("4.1.0;4.2.0   ;WEKAPP-318113;WTA 08302023;KB 1177;Batch client upgrade issues")

RETURN_CODE=0


# Use core-util's sort -V to dermine if version $1 is <= version $2
verlte() {
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}
verlt() {
    [ "$1" = "$2" ] && return 1 || verlte $1 $2
}

WEKA_VERSION=$(weka version current)

for VERSION_TO_CHECK in "${WEKA_VERSION_TABLE[@]}" ; do
    MIN_VERSION=$(   echo ${VERSION_TO_CHECK} | awk -F';' '{print $1}')
    MAX_VERSION=$(   echo ${VERSION_TO_CHECK} | awk -F';' '{print $2}')
    JIRA_REFERENCE=$(echo ${VERSION_TO_CHECK} | awk -F';' '{print $3}')
    WTA_REFERENCE=$( echo ${VERSION_TO_CHECK} | awk -F';' '{print $4}')
    KB_REFERENCE=$(  echo ${VERSION_TO_CHECK} | awk -F';' '{print $5}')
    DESCRIPTION=$(   echo ${VERSION_TO_CHECK} | awk -F';' '{print $6}')
    MIN_VERSION="${MIN_VERSION:-0.0.1}"
    MAX_VERSION="${MAX_VERSION:-999.99.9}"
    if verlte ${MIN_VERSION} ${WEKA_VERSION} && verlte ${WEKA_VERSION} ${MAX_VERSION} ; then
        RETURN_CODE=1
        echo "The current Weka version ${WEKA_VERSION} is potentially susceptible"
        if [[ ! -z "${WTA_REFERENCE}" ]]; then
            echo "to ${JIRA_REFERENCE} (${DESCRIPTION}), discussed in ${WTA_REFERENCE}, SFDC ${KB_REFERENCE}"
        else
            echo "to ${JIRA_REFERENCE} (${DESCRIPTION}), SFDC ${KB_REFERENCE}"
        fi
        echo "This does not necessarily prove a problem, and should be investigated"
        echo
    fi
done

exit ${RETURN_CODE}
