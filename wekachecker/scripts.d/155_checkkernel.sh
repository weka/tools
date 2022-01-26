#!/bin/bash

DESCRIPTION="Check if kernel is supported..."
SCRIPT_TYPE="parallel"

# Checking if running kernel is supported by weka runtime
current_kernel_result=`uname -r`

# Supported kernel versions are: 2.6.32 - 3.10.* - 4.4.* and 4.15.*
case $current_kernel_result in
	3.10*|4.4*|4.5*|4.6*|4.7*|4.8*|4.9*|4.10*|4.11*|4.12*|4.13*|4.14*|4.15*|4.16*|4.17*|4.18*|4.19*|5.3*|5.4* ) 
				write_log "Current running Kernel: $current_kernel_result is supported by Weka"
					ret="0"
					;;
				*   ) write_log "Current running Kernel: $current_kernel_result is NOT supported by Weka"
					ret="1"
					;;
esac
exit $ret
