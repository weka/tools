#!/bin/bash

DESCRIPTION="Check Firewall rules..."
SCRIPT_TYPE="parallel"

if grep "Amazon Linux" /etc/os-release &> /dev/null; then
        write_log "Not checking frewall rules because it is N/A on AWS"
        ret="0"
        exit $ret
fi

# Checking if OS has clean firewall rules
which iptables &> /dev/null
if [ $? -eq 1 ]; then
	write_log "iptables binary was not found in the system, could not test firewall rules"
	ret="1"
else
	# Check if there is a firewalld service is running 
	if [ ! -e /etc/redhat-release ]; then
		# On Debian
		count_rules=`sudo iptables -L -v -n | wc -l`
		if [ "$count_rules" -ne "8" ]; then
			write_log "Firewall has some extra rules setup, Weka.IO might not function properly, please see below ouput of iptables -L -v -n"
			running_rule=`sudo iptables -L -v -n`
			write_log "$running_rule"
			ret="1"
		else
			write_log "Firewall rules looking good"
			ret="0"
		fi
	else
		# On RedHat
		systemctl status firewalld | grep inactive &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Firewalld service is enabled: please run systemctl disable firewalld, service firewalld stop"
			ret="1"
		else
			write_log "Firewalld service is disabled."
			ret="0"
		fi
	fi
fi
exit $ret
