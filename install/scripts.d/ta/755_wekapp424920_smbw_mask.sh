#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check tsmb.conf for force_create_mode and force_directory_mode on share definitions"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-424920"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
    echo "ERROR: Not able to run weka commands"
    exit 254
elif [[ $? -eq 127 ]]; then
    echo "WEKA not found"
    exit 254
elif [[ $? -eq 41 ]]; then
    echo "Unable to login into Weka cluster"
    exit 254
fi

# Is SMBW configured?
if weka smb cluster | awk '/Type:/ && /smbw/' &> /dev/null; then
    # Is there a running smbw container?
    if weka local ps -F name=smbw -F state="Running" &> /dev/null; then
        # Is an affected version of SMBW in use?
        if weka local exec -C smbw /usr/local/bin/tsmb-server -v | grep -q 3024; then
            NUM_SHARES=$(weka local exec -C smbw cat /tmp/smbw-config-fs/.smbw/tsmb.conf | grep -e "^\[share\]" | wc -l)
            NUM_FILE_MASKS=$(weka local exec -C smbw cat /tmp/smbw-config-fs/.smbw/tsmb.conf | grep "force_create_mode" | wc -l)
            NUM_DIR_MASKS=$(weka local exec -C smbw cat /tmp/smbw-config-fs/.smbw/tsmb.conf | grep "force_directory_mode" | wc -l)

            if [[ $NUM_SHARES -ne $NUM_FILE_MASKS ]]; then
                echo "WARN: there are $NUM_SHARES smbw shares, but only $NUM_FILE_MASKS shares with force_create_mode"
                RETURN_CODE=254
            fi

            if [[ $NUM_SHARES -ne $NUM_DIR_MASKS ]]; then
                echo "WARN: there are $NUM_SHARES smbw shares, but only $NUM_DIR_MASKS shares with force_directory_mode"
                RETURN_CODE=254
            fi
        else
            echo "Not vulnerable to WEKAPP-424920 - SMBW version not affected"
        fi
    else
        echo "SMBW container not running on host -- no check required"
    fi
else
    echo "SMBW not configured -- no check required"
fi

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Not vulnerable to WEKAPP-424920 - smbw shares properly defined"
fi

exit $RETURN_CODE