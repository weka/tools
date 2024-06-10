#!/bin/bash

DESCRIPTION="Check DNS configuration..."
SCRIPT_TYPE="parallel"

# Checking OS internal DNS servers
CURRENT_DNS_SERVER=$(grep -w -m 1 nameserver /etc/resolv.conf | awk {'print $2'})
if [[ -n $CURRENT_DNS_SERVER ]]; then
	echo "Found DNS server with IP address of: $CURRENT_DNS_SERVER"
	which nslookup &> /dev/null
	if [ $? -eq 1 ]; then
		echo "Could not find nslookup utility, please install yum -y install bind-utils or apt-get install dnsutils"
		ret="254"
	else
		nslookup $CURRENT_DNS_SERVER &> /dev/null
		if [ $? -eq 1 ]; then
			echo "Unfortunately, the specified DNS found in /etc/resolv.conf would not be able to perform DNS resolution properly"
			ret="1"
		else
			echo "DNS server with IP: $CURRENT_DNS_SERVER is operational and reachable"
			ret="0"
		fi
	fi
fi

if [ "$ret" -eq 0 ]; then
  echo "All tests passed."
fi
exit $ret
