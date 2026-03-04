#!/bin/bash

set -u # Fail with an error code if there's any sub-command/variable error
set -o pipefail

DESCRIPTION="Check the weka agent is enabled"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

NUM_AGENT=0
RUN_MATCHES=0
AGENT_PID_FILE="/var/run/weka-agent.pid"

# Check if it's actually enabled
if ! systemctl is-enabled weka-agent >/dev/null 2>&1 ; then
    RETURN_CODE=254
    echo "WARN: The service weka-agent is not reported as enabled by systemd"
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
else
    if [[ -r $AGENT_PID_FILE ]]; then
        AGENT_PID=$(<"$AGENT_PID_FILE")
    fi

    while read -r PID; do
        ((NUM_AGENT++))
        if [[ -n $AGENT_PID && $PID -eq $AGENT_PID ]]; then
            RUN_MATCHES=1
        fi
    done < <(pgrep -x -f '/usr/bin/weka --agent' || true)
fi

if [[ $NUM_AGENT -gt 1 && $RUN_MATCHES -eq 0 ]]; then
    echo "WARN: weka-agent is running $NUM_AGENT times"
    echo " Recommended Resolution: ensure only 1 weka-agent is running and the"
    echo "  pid matches the one in /var/run/weka-agent.pid"
    RETURN_CODE=254
elif [[ $NUM_AGENT -gt 1 ]]; then
    echo "WARN: weka-agent is running $NUM_AGENT times"
    echo " Recommended Resolution: ensure only 1 weka-agent is running"
    RETURN_CODE=254
elif [[ $RUN_MATCHES -eq 0 ]]; then
    echo "WARN: the weka-agent pid does not match the pid in /var/run/weka-agent.pid"
    echo " Recommended Resolution: ensure the pid match to prevent complications during upgrade"
    RETURN_CODE=254
fi


if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "weka-agent is enabled"
fi
exit ${RETURN_CODE}
