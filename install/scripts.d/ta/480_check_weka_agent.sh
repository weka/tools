#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check the weka agent is enabled"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0


# Check if it's actually enabled
systemctl is-enabled weka-agent >/dev/null 2>&1

if [[ $? -ne "0" ]] ; then
    RETURN_CODE=254
    echo "The service weka-agent is not reported as enabled by systemd"
    echo "This may cause weka to fail to start"
    echo " Recommended Resolution: enable the service with systemctl enable weka-agent"
    
    if [[ ! -L /etc/init.d ]]; then
        echo "/etc/init.d is expected to be a symlink to /etc/rc.d/init.d"
        echo "Without this systemd is unable to find and thus start the weka-agent sysV init script"
        echo " Recommended Resolution: on RHEL-based OSes move any scripts to /etc/rc.d/init.d, remove"
        echo " the /etc/init.d directory, and re-create it as a link. The following commands are"
        echo " one way to achieve this"
        echo " mv /etc/init.d/* /etc/rc.d/init.d/ && rmdir /etc/init.d && ln -s /etc/rc.d/init.d /etc/init.d"
    fi
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "The weka agent is enabled"
fi
exit ${RETURN_CODE}
