#!/bin/bash

DESCRIPTION="Check for Weka Required Packages..."
SCRIPT_TYPE="parallel"

# Checking if OS has the required packages installed for proper Weka.IO runtime
install_needed=""

missing_list=()

if [[ $ID_LIKE == *rhel* ]]; then
	echo "REQUIRED packages missing for weka installation (Red Hat based system)"
	red_hat_pkg_list_weka=( "elfutils-libelf-devel" \
                             "gcc" "glibc-headers" "glibc-devel" \
                             "make" "perl" "rpcbind" "xfsprogs" \
                             "kernel-devel" )

	for i in ${red_hat_pkg_list_weka[@]}; do
		rpm -q $i &> /dev/null
		if [ $? -eq 1 ]; then
            missing_list+=($i)
			ret="1" # FAIL
            install_needed="$install_needed $i"
		fi
	done

    needed_actions="${install_needed}"
    if [[ "$FIX" == "True" && "${needed_actions}" != "" ]]; then
        echo "--fix specified, attempting to install/remove packages"
        if [ "${install_needed}" != "" ]; then
            sudo yum -y install ${install_needed}
            if [ $? -ne 0 ]; then
                echo "Failure while installing packages."
                ret="1" # FAIL
            fi
        fi
    fi

elif [[ $ID_LIKE == *debian* ]]; then
	echo "REQUIRED packages missing for weka installation (Debian/Ubuntu based system)"
	debian_pkg_list_weka=( "libelf-dev" "linux-headers-$(uname -r)" \
                            "gcc" "make" "perl" "python2-minimal" \
                            "rpcbind" "xfsprogs" )

	for i in ${debian_pkg_list_weka[@]}; do
		dpkg -l | awk {'print $2'} | grep -i $i &> /dev/null
		if [ $? -eq 1 ]; then
            missing_list+=($i)
			ret="1" # FAIL
            install_needed="$install_needed $i"
		fi
	done

    needed_actions="${install_needed}"
    if [[ "$FIX" == "True" && "${needed_actions}" != "" ]]; then
        echo "--fix specified, attempting to install/remove packages"
        if [ "${install_needed}" != "" ]; then
            sudo apt-get update
            sudo apt-get -y install ${install_needed}
            if [ $? -ne 0 ]; then
                echo "Failure while installing packages."
                ret="1" # FAIL
            fi
        fi
    fi

fi
out=" : : : "
for (( i=0; i<"${#missing_list[@]}"; i++ )); do
    out+="${missing_list[$i]}: : "
    n=i+1
    mod=$((n%5))
    if [[ $mod == "0" ]]; then
        out+="\n : : : "
    fi
done
printf "$out\n" | column -t -s ":"
printf "\n"

# Check if Python 3.6 or higher is installed. Python 3.6 is required for resource generator script.
python_required=3.6
if command -v python3 &>/dev/null; then
    python_version=$(python3 -V | awk '{print $2}')
    if [ $python_required == $(echo -e "$python_version\n$python_required" | sort -V | head -n1) ]; then
        echo "Python 3 is installed and version is $python_version, which is 3.6 or higher."
    else
        echo "Python 3 is installed but the version ($python_version) is lower than $python_required. Some tools may not work properly without python >= $python_required"
        ret="1" # FAIL
    fi
else
    echo "Python 3 is not installed. Some tools may not work properly without python >= $python_required "
    ret="1" # FAIL
fi

exit $ret
