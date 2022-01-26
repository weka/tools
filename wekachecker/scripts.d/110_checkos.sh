#!/bin/bash

DESCRIPTION="Check OS Release..."
SCRIPT_TYPE="parallel"

# Check OS version if there is redhat release file, if not, then lsb check, if no lsb, then hostnamectl
which hostnamectl &> /dev/null
if [ $? -eq 1 ]; then
	if [ -f /etc/os-release ]; then
		if grep "Amazon Linux" /etc/os-release > /dev/null; then
			OS_DISTRO="aws"
		fi
		if grep "2017.09" /etc/os-release > /dev/null; then
			OS='aws1709'
		fi
		if grep "2017.03" /etc/os-release > /dev/null; then
			OS='aws1703'
		fi
		if grep "Amazon Linux 2" /etc/os-release > /dev/null; then
			OS='aws1712'
		fi
		if grep "2017.12" /etc/os-release > /dev/null; then
			OS='aws1712'
		fi
		if grep "2018.03" /etc/os-release > /dev/null; then
			OS='aws1803'
		fi
		elif grep "SUSE Linux Enterprise" /etc/os-release > /dev/null; then
			OS_DISTRO="suse"
		if grep "SUSE Linux Enterprise Server.*12" /etc/os-release > /dev/null; then
			OS='suse12'
		fi
		if [ -z $OS_DISTRO ] && [ -z $OS ]; then
			write_log "OS dist $OS_DISTRO, release $OS is supported"
			ret="0"
		fi
	else
		write_log "Could not find hostnamectl utility, unable to check OS version properly"
		ret="1"
	fi
else
	dist=`hostnamectl | grep -i operating | awk {'print $3'}`
	osver=`hostnamectl | grep -i operating | awk -F: {'print $2" "$3" "$4'} | sed 's/ //g' | sed 's/[a-zA-Z ]//g' | sed 's/()//g'`
	if [ -z $osver ]; then
		write_log "OS release number could not be detected, setting it as 0"
		osver="0"
	fi
	
	case $dist in
		red*|cent*|Cent*|Red* ) # need to get proper version running
			if [ ! -f /etc/redhat-release ]; then
				osver="0"
			else
				osver=`cat /etc/redhat-release | sed -e 's/.*[^0-9\.]\([0-9\.]\+\)[^0-9]*$/\1/'`
			fi
			;;
	esac

	# Got some dist and osver strings in
	if [ -z $dist ] && [ -z $osver ]; then
        	echo "Could not find Dist or OS version running"
        	ret="1"
	else
        	# Checking if the version and OS are supported by Weka.IO requirements
        	check_dist=`echo $dist | sed 's/[a-zA-Z]/\L&/g'`
        	check_osver=`echo $osver | sed 's/[a-zA-Z ]//g'`
        	case $check_dist in
			debian) case $check_osver in
				9.7* | 9.8* ) write_log "OS $check_dist and version $check_osver are supported"
					ret="0"
					;;
				*) write_log "OS $check_dist and version $check_osver are not supported"
					ret="1"
					;;
			esac
                        ;;
			red*|cent*) case $check_osver in
				7.2* | 7.3* | 7.4* | 7.5* | 7.6* | 7.7* | 7.8* | 7.9* | 8.0* | 8.1* | 8.2* ) write_log "OS $check_dist and version $check_osver are supported"
					ret="0"
					;;
				*) write_log "OS $check_dist and version $check_osver are not supported"
					ret="1"
					;;
			esac
			;;
			aws*|amazon*|Amazon*) case $check_osver in
				1703 | 1709 | 1712 | 1803 | 2 | Linux ) write_log "OS $check_dist and version $check_osver are supported"
					ret="0"
					;;
				*) write_log "OS $check_dist and version $check_osver are not supported"
					ret="1"
					;;
			esac
			;;
			ubuntu*) case $check_osver in
				16* | 18* | 20* ) write_log "OS $check_dist and version $check_osver are supported"
					ret="0"
					;;
				*) write_log "OS $check_dist and version $check_osver are not supported"
					ret="1"
					;;
			esac
			;;
			*) write_log "OS type: $check_dist. This version of OS is currently unsupported by Weka.IO"
				ret="1"
				;;
        	esac
	fi
fi

exit $ret
