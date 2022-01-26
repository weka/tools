#!/bin/bash

DESCRIPTION="Check if OS has SELinux disabled or in permissive mode"
SCRIPT_TYPE="parallel"

# Checking if OS has SELinux enabled or in permissive mode
NOT_DISABLED="False"
which sestatus &> /dev/null
if [ $? -eq 1 ]; then
	write_log "SELinux tool not found in the system, it is either disabled or not available"
	ret="0"
else
	# Checking AWS condition where sestatus found, but not available in /etc/selinux/config
	if [ ! -f /etc/selinux/config ]; then
		which getenforce &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Could not find getenforce tool to get SELinux status"
			ret="1"
		else
			conf_status=`getenforce`
			if [[ "$conf_status" -ne "Disabled" ]] || [[ "$conf_status" -ne "Permissive" ]]; then
				write_log "The current SELinux configuration status would not allow Weka.IO to run properly"
				ret="1"
			else
				ret="0"
			fi
		fi
	else
		# Found selinux config file
		seconfstat=`cat /etc/selinux/config | grep -i selinux|grep -v "#"|head -1|awk -F= {'print $2'}`
		which getenforce &> /dev/null
		if [ $? -eq 0 ]; then
			securstat=`getenforce`
			if [[ "$securstat" -ne "Permissive" ]] || [[ "$securstat" -ne "Disabled" ]]; then
				write_log "SELinux configuration seem to be configured to $seconfstat and running status is $securstat and this might cause some issues with Weka runtime"
				NOT_DISABLED="True"
				ret="1"
			else
				write_log "SELinux configuration seem to be OK and set to $securstat"
				ret="0"
			fi
		else
			securstat="$seconfstat"
			if [[ "$seconfstat" -ne "disabled" ]] || [[ "$seconfstat" -ne "Disabled" ]]; then
				write_log "SELinux configuration seem to be configured to $seconfstat and this might cause some issues with Weka runtime"
				NOT_DISABLED="True"
				ret="1"
			else
				write_log "SELinux configuration seem to be OK and set to $seconfstat"
				ret="0"
			fi
		fi

		# Fix it?
		if [[ "$NOT_DISABLED" == "True" && "$FIX" == "True" ]]; then
			echo "SELINUX=disabled" >> /etc/selinux/config
			write_log "SELINUX disabled.  Reboot required to enable the new config."
			ret="254"
		fi
	fi
fi
exit $ret
