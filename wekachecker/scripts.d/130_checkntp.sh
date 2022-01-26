#!/bin/bash

DESCRIPTION="Check for NTP..."
SCRIPT_TYPE="parallel"

# General requirement is to have time synced for all Weka.IO cluster nodes, since this script is running as standalone on per node basis, it would check if there is NTP running and if time is synced properly

echo $PATH
CHRONY=0
NTP=0

which chronyc &> /dev/null
if [ $? -eq 0 ]; then
	CHRONY=1
fi

which ntpdate &> /dev/null
if [ $? -eq 0 ]; then
	NTP=1
fi

if [ $CHRONY -eq 1 ] && [ $NTP -eq 1 ]; then
	write_log "Both Chrony and NTP are installed"
elif [ $CHRONY -eq 1 ]; then
	write_log "Chrony is installed"
elif [ $NTP -eq 1 ]; then
	write_log "NTP is installed"
else
	write_log "Neither Chrony nor NTP are installed"
fi

CHRONYGOOD=0
if [ $CHRONY -eq 1 ]; then
	chronyc waitsync 1 0.1 &> /dev/null
	if [ $? -eq 0 ]; then
		write_log "Chrony is working"
		CHRONYGOOD=1
		exit 0
	else
		write_log "Chrony installed but not working"
	fi
fi

# if we're here, chrony is installed but not working for some reason; maybe NTP was installed and is working?
NTPGOOD=0
if [ $NTP -eq 1 ]; then
	ntpdate -q time.nist.gov &> /dev/null
	if [ $? -eq 1 ]; then
		write_log "NTP installed but not working?"
	else
		sec_ntp=`ntpdate -q time.nist.gov | tail -1 | awk {'print $10'} | awk -F. {'print $1'}`
		if [ "$sec_ntp" -ne "0" ]; then
			write_log "Time is unsynced for more than a second, please run: ntpdate -b time.nist.gov"
		else
			write_log "Time is properly synced"
			NTPGOOD=1
		fi
	fi
fi

if [ $CHRONY -eq 0 ] && [ $NTP -eq 0 ]; then
	ret=1
fi

exit $ret
