#!/bin/bash

DESCRIPTION="Check OS Release..."
SCRIPT_TYPE="parallel"

# Currently supported releases:
## https://docs.weka.io/support/prerequisites-and-compatibility

distro_not_found=0
version_not_found=0
unsupported_distro=0
unsupported_version=0
warning=0
client_only=0

case $ID in
	'centos')
		case $VERSION_ID in
			'7.'[2-9]) ;;
			'8.'[0-7]) ;;
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'rhel')
		case $VERSION_ID in 
			'7.'[2-9]) ;;
			'8.'[0-6]) ;;
			'9.'[0-1]) client_only=1 ;; # change to warning=1 when RHEL 9 is supported
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'rocky')
		case $VERSION_ID in 
			'8.'[0-7]) ;;
			'9.'[0-1]) client_only=1 ;; # change to warning=1 when RHEL 9 is supported
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	# SLES Service Packs are registered as point releases, i.e. SLES 12 SP5 becomes "12.5"
	'sles')
		case $VERSION_ID in
			'12.5') client_only=1 ;;
			'15.2') client_only=1 ;;
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'ubuntu')
		case $VERSION_ID in
			'18.04.'[0-6]) ;;
			'20.04.'[0-6]) ;;
			'22.04.'[0-4]) client_only=1 ;;
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'') distro_not_found=1 ;;
	*) unsupported_distro=1 ;;
esac

if [ "$distro_not_found" -eq 1 ]; then
	echo 'Distribution not found'
	exit 1
elif [ "$version_not_found" -eq 1 ]; then
	echo "$NAME detected but version not found"
	exit 1
elif [ "$unsupported_distro" -eq 1 ]; then
	echo "$NAME is not a supported distribution"
	exit 1
elif [ "$unsupported_version" -eq 1 ]; then
	echo "$NAME $VERSION_ID is not a supported version of $NAME"
	exit 1
elif [ "$warning" -eq 1 ]; then
	echo "$NAME $VERSION_ID version of $NAME is newly supported, please verify OS compatibility"
	exit 254
else
	if [ "$client_only" -eq 1 ]; then
		echo "$NAME $VERSION_ID is supported (for client only)"
		exit 254
	else
		echo "$NAME $VERSION_ID is supported"
		exit 0
	fi
fi
