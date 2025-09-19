#!/bin/bash

DESCRIPTION="Check for Weka Required Packages"
SCRIPT_TYPE="parallel"

# Checking if OS has the required packages installed for proper Weka.IO runtime
install_needed=()
missing_list=()
ret=0

OS=$(grep -oP '(?<=VERSION_ID=")[^"]*' /etc/os-release | cut -d. -f1)

# Red Hat based system                      
if [[ $ID_LIKE == *rhel* ]]; then
    echo "REQUIRED packages missing for Weka installation (Red Hat based system)"
    red_hat_pkg_list_weka=("elfutils-libelf-devel" "gcc" "glibc-headers" "glibc-devel" "make" "perl" "xfsprogs" "kernel-devel")

    for pkg in "${red_hat_pkg_list_weka[@]}"; do
        if ! rpm -q "$pkg" &> /dev/null; then
            missing_list+=("$pkg")
            ret=1 #FAIL
            install_needed+=("$pkg")
        fi
    done

    if [[ "$FIX" == "True" && ${#install_needed[@]} -gt 0 ]]; then
        echo "--fix specified, attempting to install/remove packages"
        if ! sudo yum -y install "${install_needed[@]}"; then
            echo "Failure while installing packages."
            ret=1 #FAIL
        fi
    fi

# Debian/Ubuntu based system                            
elif [[ $ID_LIKE == *debian* ]]; then
    echo "REQUIRED packages missing for Weka installation (Debian/Ubuntu based system)"
    if (( $OS >= 24 )); then
        minimal_python="python3-minimal"
    elif (( $OS >= 20 )); then
        minimal_python="python2-minimal"
    else
        minimal_python="python-minimal"
    fi
    debian_pkg_list_weka=("libelf-dev" "linux-headers-$(uname -r)" "gcc" "make" "perl" "$minimal_python" "xfsprogs")
    for pkg in "${debian_pkg_list_weka[@]}"; do
        if ! dpkg -l | awk '{print $2}' | grep -i "$pkg" &> /dev/null; then
            missing_list+=("$pkg")
            ret=1 #FAIL
            install_needed+=("$pkg")
        fi
    done

    if [[ "$FIX" == "True" &&  ${#install_needed[@]} -gt 0 ]]; then
        echo "--fix specified, attempting to install/remove packages"
        sudo apt-get update
        if ! sudo apt-get -y install "${install_needed}"; then
            echo "Failure while installing packages."
            ret=1 #FAIL
        fi
    fi

fi
# Output missing packages
out=" : : : "
for (( i=0; i<"${#missing_list[@]}"; i++ )); do
    out+="${missing_list[$i]}: : "
    if (( (i+1) % 5 == 0 )); then
        out+="\n : : : "
    fi
done
printf "$out\n" | column -t -s ":"
printf "\n"

# Check if Python 3.6 or higher is installed. Python 3.6 is required for resource generator script.
python_required="3.6"
if command -v python3 &>/dev/null; then
    python_version=$(python3 -V | awk '{print $2}')
    # Use sort -V for version comparison
    if [[ "$(echo -e "$python_version\n$python_required" | sort -V | head -n1)" != "$python_required" ]]; then
        echo "Python 3 is installed but the version ($python_version) is lower than $python_required. Some tools may not work properly without python >= $python_required"
        ret=1 #FAIL
    else
        echo "Python 3 is installed and version is $python_version, which is 3.6 or higher."
    fi
else
    echo "Python 3 is not installed. Some tools may not work properly without python >= $python_required "
    ret=1 #FAIL
fi

exit $ret
