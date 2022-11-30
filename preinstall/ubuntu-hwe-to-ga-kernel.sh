#!/bin/bash

script_name=$(basename "$0")

declare -A ga_kernels=(
	['18.04']='4.15'
	['20.04']='5.4'
	['22.04']='5.15'
)
. /etc/os-release  # For VERSION_ID, e.g. '20.04'
prompt=''  # Unset, i.e. do not prompt

get_installed_kernels() {
	dpkg -l | awk '/^ii  linux-image-[0-9]/ { print $2 }' | rev | cut -d '-' -f '-3' | rev | grep -vE '[0-9]$' | sort -Vu
}

get_kernels_to_remove() {
	if [ "${ga_kernels[$VERSION_ID]}" ]; then
		echo "$installed_kernels" | grep -v "${ga_kernels["$VERSION_ID"]}"
	else
		>&2 echo 'Unsupported Linux distribution or Ubuntu version' && exit 1
	fi
}

remove_kernels() {
	local package_glob=$(echo "$@" | sed 's/^/*/g; s/ / */g')
	local packages=$(dpkg -l "$package_glob" | awk '/^ii/ { print $2 }')
	echo 'Marking packages as manually installed...'
	sudo apt-mark manual $packages
	echo
	sudo apt-get $prompt purge $packages
}

install_ga_kernel() {
	sudo apt-get update
	sudo apt-get $prompt install linux-generic
}

usage() {
	cat <<- EOF
	Usage: $script_name [ -d | --dry-run ] [ -y | --yes ]

	This script will check and remove HWE kernels from the system, and install
	the general availability (GA) kernel. Removing the HWE kernels will also
	remove the HWE metapackage (i.e. linux-generic-hwe-$VERSION_ID), of which the
	HWE kernel packages are dependencies, preventing further HWE kernels being
	installed automatically.

	It is recommended that the following is run first to determine what the
	script is going to do (and to review this carefully):

	    $script_name --dry-run 

	If the script prints similar to the following:

	    Packages for the running kernel ($(uname -r)) will be removed.
	    You will be prompted to confirm whether you wish to abort this
	    (select \`<No>\`) and a reboot will be required.

	It will need to be run interactively; \`-y\` will not suppress the above (but
	will suppress package installation/removal confirmation).

	Note that this version of the script does not remove generic (i.e
	non-CPU-architecture-specific) header packages nor does it autoremove
	packages. You may see output similar to the following:

	    The following packages were automatically installed and are no longer required:
	      linux-headers-4.15.0-156 linux-headers-4.15.0-156-generic
	      linux-hwe-5.4-headers-5.4.0-132 linux-image-4.15.0-156-generic
	      linux-modules-4.15.0-156-generic linux-modules-extra-4.15.0-156-generic
	    Use 'sudo apt autoremove' to remove them.

	Follow the guidance in the output to resolve this, or simply remove these
	packages specifically.

	Options:
	    -d, --dry-run
	        Only print kernels that would be removed.
	    -y, --yes
	        Skip all prompts.
	    -h, --help
	        Show this help/usage message. Cancels out all other options.
	EOF
}

main() {
	arg_error=0
	dry_run=0
	print_usage=0

	# Prompt for sudo now rather than later
	sudo -v

	# Convert long options to short options, stick them back on the end of $@
	for arg in $@; do
		case $arg in
			--dry-run) set -- "$@" '-d' ;;
			--yes) set -- "$@" '-y' ;;
			--help) set -- "$@" '-h' ;;
			--*)
				>&2 echo "$script_name: illegal long option -- ${arg:2}"
				arg_error=1
				;;
			*) set -- "$@" "$arg" ;;
		esac
		shift
	done

	# Cycle through options, setting positional arguments as they are found
	while [ "$OPTIND" -le "$#" ]; do
		if getopts 'dyh' opts; then
			case $opts in
				d) dry_run=1 prompt='-y' ;;
				y) prompt='-y' ;;
				h) print_usage=1 ;;
				?) arg_error=1 ;;
			esac
		else
			args="${args# } ${@:$OPTIND:1}"
			((OPTIND++))
		fi
	done

	[ "$arg_error" -ne 0 ] && >&2 usage && exit 1
	[ "$print_usage" -eq 1 ] && usage && exit 0

	installed_kernels=$(get_installed_kernels)
	kernels_to_remove=$(get_kernels_to_remove)

	printf "Current kernel: $(uname -r)\n\n"
	printf "Installed kernels:\n$installed_kernels\n\n"

	if [ ! "$kernels_to_remove" ]; then
		echo 'No kernels to remove.'
		exit 0
	else
		printf "Kernels to be removed:\n$kernels_to_remove\n\n"

		if [[ $kernels_to_remove = *"$(uname -r)"* ]]; then
			echo "Packages for the running kernel ($(uname -r)) will be removed."
			echo 'You will be prompted to confirm whether you wish to abort this' 
			echo '(select `<No>`) and a reboot will be required.'
			[ "$dry_run" -eq 1 ] && exit 0
			echo

			if [ "$prompt" = '-y' ]; then
				sleep 3
				remove_kernels $kernels_to_remove
			else
				read -n 1 -p 'Do you wish to continue removing these kernels? [y|N] ' input
				echo
				case $input in
					[Yy]) echo; remove_kernels $kernels_to_remove ;;
					[Nn]) echo "Exiting..."; exit 0 ;;
					*) echo "Exiting..."; exit 1 ;;
				esac
			fi
		fi
	
		[ "$dry_run" -eq 1 ] && exit 0
	fi

	echo 'Installing the General Availability (GA) kernel metapackage. This will'
	echo 'install the latest GA kernel packages.'
	install_ga_kernel
}

main "$@"
