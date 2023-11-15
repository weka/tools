#!/bin/bash

DESCRIPTION="Check DNS configuration..."
SCRIPT_TYPE="parallel"

# Checking OS internal DNS servers
current_dns_server=`cat /etc/resolv.conf | grep -i nameserver | awk {'print $2'}`
if [ ! -z $current_dns_server ]; then
	echo "Found DNS server with IP address of: $current_dns_server"
	which nslookup &> /dev/null
	if [ $? -eq 1 ]; then
		echo "Could not find nslookup utility, please install yum -y install bind-utils or apt-get install dnsutils"
		ret="254"
	else
		nslookup $current_dns_server &> /dev/null
		if [ $? -eq 1 ]; then
			echo "Unfortunately, the specified DNS found in /etc/resolv.conf would not be able to perform DNS resolution properly"
			ret="1"
		else
			echo "DNS server with IP: $current_dns_server is operational and reachable"
			ret="0"
		fi
	fi
fi

exit $ret
