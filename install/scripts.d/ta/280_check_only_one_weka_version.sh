#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that only one Weka version is installed"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
    echo "ERROR: Not able to run Weka commands."
    exit 254
elif [[ $? -eq 127 ]]; then
    echo "Weka not found."
    exit 254
elif [[ $? -eq 41 ]]; then
    echo "Unable to login into Weka cluster."
    exit 254
fi


NUMBER_OF_WEKA_VERSIONS=$(weka version | wc -l)
if [[ ${NUMBER_OF_WEKA_VERSIONS} -ne 1 ]] ; then

    CONTAINER_LIST_FILE="/tmp/weka_cluster_container_versions.txt.${RANDOM}"
    # Get the current list of container versions, in case we have older clients
    (weka cluster container --output release --no-header ; weka cluster client-target-version show) | sort | uniq > ${CONTAINER_LIST_FILE} 2>/dev/null

    NUMBER_OF_POSSIBLY_REDUNDANT_WEKA_VERSIONS=$(weka version | grep -v -f ${CONTAINER_LIST_FILE} | wc -l)
    if [[ ${NUMBER_OF_POSSIBLY_REDUNDANT_WEKA_VERSIONS} -ne 1 ]] ; then
        echo "There is more than one Weka version installed - this is usually a remnant"
        echo "of previous upgrades and not removing older versions".
        echo "The non-default versions can be removed from each node individually, if required, with: "
        for NON_DEFAULT_WEKA_VERSION in $(weka version | grep -v "^*") ; do
            echo "    weka version rm ${NON_DEFAULT_WEKA_VERSION}"
        done
        RETURN_CODE=254
    else
        echo "More than one Weka version is installed, but they're all in use according to cluster members"
    fi

    rm -f ${CONTAINER_LIST_FILE}
fi 
if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Only one Weka version is installed"
fi
exit ${RETURN_CODE}


