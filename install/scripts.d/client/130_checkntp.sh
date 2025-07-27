#!/bin/bash

DESCRIPTION="Check for NTP/Chrony/timesyncd..."
SCRIPT_TYPE="parallel"

# General requirement is to have time synced for all Weka.IO cluster nodes, since this script is running as standalone on per node basis, it would check if there is NTP running and if time is synced properly

CHRONY=0
NTP=0
TIMESYNCD=0

which chronyc &> /dev/null
if [ $? -eq 0 ]; then
	CHRONY=1
fi

which ntpdate &> /dev/null
if [ $? -eq 0 ]; then
	NTP=1
fi

systemctl status systemd-timesyncd &> /dev/null
if [ $? -eq 0 ]; then
	TIMESYNCD=1
fi

if [ $CHRONY -eq 1 ] && [ $NTP -eq 1 ]; then
	echo "Both Chrony and NTP are installed"
elif [ $CHRONY -eq 1 ]; then
	echo "Chrony is installed"
elif [ $NTP -eq 1 ]; then
	echo "NTP is installed"
elif [ $TIMESYNCD -eq 1 ]; then
	echo "Timesyncd is running"
else
	echo "Neither Chrony, timesyncd nor NTP are installed"
	echo "    PATH: $PATH"
fi

CHRONYGOOD=0
if [ $CHRONY -eq 1 ]; then
	chronyc waitsync 1 0.1 &> /dev/null
	if [ $? -eq 0 ]; then
		echo "Chrony is working"
		CHRONYGOOD=1
		exit 0
	else
		echo "Chrony installed but not working"
	fi
fi

# if we're here, chrony is installed but not working for some reason; maybe NTP was installed and is working?
NTPGOOD=0
if [ $NTP -eq 1 ]; then
	ntpdate -q time.nist.gov &> /dev/null
	if [ $? -eq 1 ]; then
		echo "NTP installed but not working?"
	else
		sec_ntp=`ntpdate -q time.nist.gov | tail -1 | awk {'print $10'} | awk -F. {'print $1'}`
		if [ "$sec_ntp" -ne "0" ]; then
			echo "Time is unsynced for more than a second, please run: ntpdate -b time.nist.gov"
		else
			echo "Time is properly synced"
			NTPGOOD=1
		fi
	fi
fi

TIMESYNCDGOOD=0
if [ $TIMESYNCD -eq 1 ]; then
	status=$(timedatectl timesync-status 2>/dev/null | grep 'Leap' | awk '{print $2}')
	if [ "$status" = "normal" ]; then
		echo "Timesync shows time is properly synced"
		TIMESYNCDGOOD=1
	else
		echo "Timesyncd installed but not working?"
	fi
fi


if [ $CHRONY -eq 0 ] && [ $NTP -eq 0 ] && [ $TIMESYNCD -eq 0 ] ; then
	ret=1
fi

exit $ret
