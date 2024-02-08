#!/bin/bash

DESCRIPTION="Check Firewall rules..."
SCRIPT_TYPE="parallel"

ret=0
if grep "Amazon Linux" /etc/os-release &> /dev/null; then
        echo "Not checking frewall rules because it is N/A on AWS"
        ret="0"
        exit $ret
fi

# Checking if OS has clean firewall rules
which iptables &> /dev/null
if [ $? -eq 1 ]; then
	echo "iptables binary was not found in the system, could not test firewall rules"
	ret="1"
else
	# Check if there is a firewalld service is running 
	if [ ! -e /etc/redhat-release ]; then
		# On Debian
		count_rules=`sudo iptables -L -v -n | wc -l`
		if [ "$count_rules" -ne "8" ]; then
			echo "Firewall has extra rules setup; Weka.IO may not function properly. Please see below ouput of iptables -L -v -n"
			running_rule=`sudo iptables -L -v -n`
			echo "$running_rule"
			ret="1"
		else
			echo "Firewall rules looking good"
			ret="0"
		fi
	else
		# On RedHat
		systemctl status firewalld | grep inactive &> /dev/null
		if [ $? -eq 1 ]; then
			echo "Firewalld service is enabled: please verify firewall rules are not blocking Weka.IO traffic"
			ret="254"
		else
			echo "Firewalld service is disabled."
			ret="0"
		fi
	fi
fi
exit $ret
