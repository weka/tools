#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that only one Weka version is installed"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"

RETURN_CODE=0

NUMBER_OF_WEKA_VERSIONS=$(weka version | wc -l)
if [[ ${NUMBER_OF_WEKA_VERSIONS} -ne 1 ]] ; then
    echo "There is more than one Weka version installed - this is usually a remnant"
    echo "of previous upgrades and not removing older versions".
    echo "The non-default versions can be removed if required with: "
    for NON_DEFAULT_WEKA_VERSION in $(weka version | grep -v "^*") ; do
        echo "    weka version rm ${NON_DEFAULT_WEKA_VERSION}"
    done
    RETURN_CODE=254
fi 

exit ${RETURN_CODE}


