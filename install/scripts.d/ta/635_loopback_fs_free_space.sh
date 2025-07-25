#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Ensure loopback filesystems in /opt/weka have free space"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-527332"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

which mkfs.xfs &> /dev/null
if [ $? == 1 ]; then
    echo "ERROR: XFS not installed"
    exit 255
else
    echo "XFS installed"
    ret="0"
fi

main() {
    if [[ ! -d /opt/weka ]] ; then
        exit 0 # No need to check further if /opt/weka doesn't exist
    fi
    for LOOPBACK_FILE in $(find /opt/weka -name \*.loop) ; do
        BLOCKS=$(xfs_info ${LOOPBACK_FILE}|grep ^data.*blocks -m1 | sed 's/^.*blocks=\([0-9][0-9]*\).*/\1/')
        FREE_BLOCKS=$(xfs_db -frc "freesp -s" ${LOOPBACK_FILE} |grep "total free blocks" | sed 's/[^0-9]*//g')
        AVAILABLE=$(awk -v total=${BLOCKS} -v free=${FREE_BLOCKS} 'BEGIN { printf "%.0f", ((free / total) * 100) }')
        if [[ ${AVAILABLE} -le 10 ]] ; then
            echo "The loopback filesystem at ${LOOPBACK_FILE} is reporting only ${AVAILABLE}% available space"
            echo "This can lead to problems starting weka"
            RETURN_CODE=254
        fi
    done

    exit ${RETURN_CODE}
}

main "$@"
