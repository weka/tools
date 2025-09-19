#!/bin/bash

DESCRIPTION="Check OS Release"
SCRIPT_TYPE="parallel"

# Currently supported releases:
## https://docs.weka.io/support/prerequisites-and-compatibility

distro_not_found=0
version_not_found=0
unsupported_distro=0
unsupported_version=0
warning=0
client_only=0

echo Version_Id $VERSION_ID
echo ID $ID

case $ID in
	'weka')
		;;

	'centos')
		case $VERSION_ID in
			'8.'[0-5]) ;;
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'rhel')
		case $VERSION_ID in 
			'8.'[0-9]) ;;
			'8.10') ;;
			'9.'[0-6]) ;; # change to warning=1 when RHEL 9 is supported
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'rocky')
		case $VERSION_ID in
			'8.'[0-9]) ;;
			'8.10') ;;
			'9.'[0-4]) ;; # change to warning=1 when RHEL 9 is supported
			'9.6') ;;
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'oracle')
		case $VERSION_ID in
			'8.5') ;;
			'8.7') ;;
			'8.9') ;;
			'9.0') ;; # change to warning=1 when RHEL 9 is supported
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'alma')
		case $VERSION_ID in 

			'8.10') client_only=1 ;;
			'9.'[4-6]) client_only=1 ;; # change to warning=1 when RHEL 9 is supported
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	# SLES Service Packs are registered as point releases, i.e. SLES 12 SP5 becomes "12.5"
	'sles')
		case $VERSION_ID in
			'12.5') client_only=1 ;;
			'15.1') client_only=1 ;;
			'15.'[3-6]) client_only=1 ;;
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

	'ubuntu')
		case $VERSION_ID in
			'18.04.'[0-6]) ;;
			'20.04.'[0-3]) ;;
			'22.04'*) ;;
			'24.04'*) ;;
			'') version_not_found=1 ;;
			*) unsupported_version=1 ;;
		esac
		;;

  'debian')
		case $VERSION_ID in
			'10') ;;
			'12') ;;
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
	exit 254
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
