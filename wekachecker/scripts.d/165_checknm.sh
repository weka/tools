#!/bin/bash

DESCRIPTION="Check if Network Manager is disabled"
SCRIPT_TYPE="parallel"

# Check if Network Manager is disabled or uninstalled
systemctl list-unit-files | grep -i "networkmanager" &> /dev/null
if [ $? -eq 1 ]; then
        write_log "Network Manager is not installed"
        ret="0"
else
        systemctl list-unit-files | grep -i "networkmanager" | head -1 | grep -i "disabled" &> /dev/null
        if [ $? -eq 1 ]; then
                write_log "System have Network Manager enabled in systemctl, please stop and disable Network manager by issuing systemctl stop NetworkManager && systemctl disable NetworkManager"
                ret="1"
		if [ "$FIX" == "True" ]; then
			sudo systemctl disable NetworkManager
			write_log "NetworkManager disabled"
			ret="254"
		fi
        else
                write_log "System have Network Manager installed, but it is disabled"
                ret="0"
        fi
fi

exit $ret
