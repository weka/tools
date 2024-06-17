#!/bin/bash

# Option/argument processing configuration
print_usage_on_arg_err=0
raw_mode_support=0

# For multi-line error messages, e.g. this style of output, where "example.sh"
# is $0:
# example.sh: Error encountered
#             More error info here
error_indent=$(for i in $(seq 1 "${#0}"); do printf ' '; done)

script_name=$(basename "$0")

usage() {
	cat <<- EOF
	Usage: $script_name [ -e | -i ] PORT [ PORT ... ]

	Changes ports to the specified type. To specify different ports types for
	different ports, run this utility multiple times.

	Options:
	    -e, --eth
	        Set port type to Ethernet.

	    -i, --ib
	        Set port type to InfiniBand.

	    -h, --help
	        Show this help/usage message.
	EOF
}

main() {
	arg_error=0
	print_usage=0
	raw=0

	# Check for raw mode, remove it from $@
	# We require --raw as the first argument:
	# - To avoid future clashes with "<UNDERLYING_UTILITY>" options
	# - As we don't parse further input
	# - As parsing further input would require knowing if an opt takes args
	# $arg will get passed directly through to "<UNDERLYING_UTILITY>" later
	if [ "$1" = '--raw' ] && [ "$raw_mode_support" -ne 0 ]; then
		raw=1
		shift
	fi

	# Raw mode
	if [ "$raw" -eq 1 ]; then
		if [ -z "$@" ]; then
			echo 'Raw mode. No further opts/args provided.'
		else
			echo "Raw mode. Input provided: $@"
		fi

	# Normal mode
	else
		# Convert long options to short options, stick them back on the end of $@
		for arg in $@; do
			case $arg in
				--e*) set -- "$@" '-e' ;;
				--i*) set -- "$@" '-e' ;;
				--help) set -- "$@" '-h' ;;
				--raw)
					if [ "$raw_mode_support" -eq 0 ]; then
						>&2 echo "$0: --raw must be first argument"
					else
						>&2 echo "$0: illegal long option -- ${arg:2}"
					fi
					arg_error=1
					;;
				--*)
					>&2 echo "$0: illegal long option -- ${arg:2}"
					arg_error=1
					;;
				*) set -- "$@" "$arg" ;;
			esac
			shift
		done

		eth=0 ib=0

		# Cycle through options setting corresponding variables as options are
		# found, or otherwise extract positional arguments
		while [ "$OPTIND" -le "$#" ]; do
			if getopts 'eih' opts; then
				case $opts in
					e) eth=1 link_type=2;;
					i) ib=1 link_type=1;;
					h) print_usage=1 ;;
					?) arg_error=1 ;;
				esac
			else
				pos_args+=("${!OPTIND}")
				((OPTIND++))
			fi
		done

		# Set $@ to positional arguments only now that we have processed options
		set -- ${pos_args[*]}
		unset pos_args

		if [ "$eth" -eq 1 ] && [ "$ib" -eq 1 ]; then
			>&2 echo "$0: multiple port types specified"
			arg_error=1
		fi

		if [ -z "$1" ] && [ "$print_usage" -ne 1 ]; then
			>&2 echo "$0: no ports specified"
			arg_error=1
		fi

		if [ "$arg_error" -ne 0 ]; then
			[ "$print_usage_on_arg_err" -eq 1 ] && >&2 usage && exit 1
			[ "$print_usage" -eq 1 ] && usage && exit 1
			exit 1
		fi

		[ "$print_usage" -eq 1 ] && usage && exit 0

		mst start || >&2 echo "$0: error starting MST, exiting"

		# If not at least one argument; using $@ instead results in `binary
		# operator expected` errors if an option is used (e.g. `-f`)
		for port in $@; do
			sysfs_port_path=$(readlink -f /sys/class/net/"$port"/device/)
			port_pci_addr=$(basename "$sysfs_port_path")
			port_pci_num=${port_pci_addr##*.}
			port_num=$((port_pci_num + 1))

			dev_pci_addr=${port_pci_addr%%.*}
			device_file=$(mst status | grep -B 1 "$dev_pci_addr" | awk '{ print $1; exit }')

			mlxconfig -d "$device_file" set "LINK_TYPE_P$port_num=$link_type"
		done

		mst stop

		echo 'Reboot to complete port type change'
	fi
}

main "$@"

# vim: set filetype=sh:
