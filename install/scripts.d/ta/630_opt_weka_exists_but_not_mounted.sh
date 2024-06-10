#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Ensure /opt/weka is mounted if it's defined and vice-versa"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC #13589"
RETURN_CODE=0

main() {
    if [[ ! -d /opt/weka ]] ; then
        exit 0 # No need to check further if /opt/weka doesn't exist
    fi
    BOOTTIME_MOUNT_EXISTS=0
    OPT_WEKA_MOUNTED=0

    # Systemd requires that an /opt/weka mount be called opt-weka.mount
    if systemctl list-units -t mount --all | grep -q '\<opt-weka\.mount' ; then BOOTTIME_MOUNT_EXISTS=1 ; fi
    if grep -q '\</opt/weka\>' /etc/fstab                                ; then BOOTTIME_MOUNT_EXISTS=1 ; fi

    # But is it actually mounted?
    if awk '$2 == "/opt/weka"' /etc/mtab | grep -q weka ; then OPT_WEKA_MOUNTED=1 ; fi

    if [[ ${OPT_WEKA_MOUNTED} -ne ${BOOTTIME_MOUNT_EXISTS} ]] ; then
        echo "Either /opt/weka exists but is not defined in systemd or /etc/fstab,"
        echo "or vice-versa."
        echo
        echo "This means that changes made to the live system as it is now"
        echo "are unlikely to be present on the system post-reboot"
        RETURN_CODE=254
    else
        echo "No immediate directory/mount overlaps found"
    fi

    exit ${RETURN_CODE}
}

main "$@"
