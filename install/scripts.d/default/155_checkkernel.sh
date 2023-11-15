#!/bin/bash

DESCRIPTION="Check if kernel is supported..."
SCRIPT_TYPE="parallel"

# Spaces required around the value as we search for " x.x "
weka_supported_kernels=$(echo ' '3.10 4.{4..19} 5.{3..15}' ')
declare -A ubuntu_ga_kernel=(
	['18.04']='4.15'
	['20.04']='5.4'
	['22.04']='5.15'
)
. /etc/os-release
kernel=$(uname -r | cut -d '.' -f 1,2)

if [[ $weka_supported_kernels == *' '$kernel' '* ]]; then
	# Warn if running Ubuntu LTS with HWE kernel
	if [[ "$PRETTY_NAME" == Ubuntu*LTS ]] && [ "$kernel" != ${ubuntu_ga_kernel["$VERSION_ID"]} ]; then
		echo "Current running kernel ($kernel) is supported by Weka but is not the"
		echo "general availability (GA) kernel for Ubuntu $VERSION_ID. This machine"
		echo 'might be running the HWE kernel, and therefore the kernel version'
		echo "*might* change to a version unsupported by Weka during Ubuntu $VERSION_ID"
		echo 'updates. Visit https://ubuntu.com/about/release-cycle#ubuntu-kernel-release-cycle'
		echo 'to verify this, and if required, use'
		echo 'https://github.com/weka/tools/tree/master/preinstall/ubuntu-hwe-to-ga-kernel.sh'
		echo 'to fix this.'
		ret=1

	else
		echo "Current running kernel ($kernel) is supported by Weka"
		ret=0
	fi

else
	echo "Current running kernel ($kernel) is NOT supported by Weka"
	ret=1
fi

exit "$ret"
