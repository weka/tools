#!/bin/bash

DESCRIPTION="Check for required Packages..."
SCRIPT_TYPE="parallel"

# Checking if OS has the required packages installed for proper Weka.IO runtime
install_needed=""
remove_needed=""

if [ "$DIST" == "redhat" ]; then
	write_log "Running on top of Red Hat based system"
	red_hat_pkg_list_weka=( "elfutils-libelf-devel" "glibc" "glibc-headers" "glibc-devel" \
		"gcc" "make" "perl" "rpcbind" )
	red_hat_pkg_list_ofed=( "pciutils" "gtk2" "atk" "cairo" "gcc-gfortran" "tcsh" "lsof" "tcl" "tk" )
	red_hat_pkg_list_general=( "epel-release" "sysstat" "strace" "ipmitool" "tcpdump" "telnet" "nmap" "net-tools" \
        "dstat" "numactl" "numactl-devel" "python" "python3" "automake" "libaio" "libaio-devel" "perl" \
        "lshw" "hwloc" "pciutils" "lsof" "wget" "bind-utils" "vim-enhanced" "nvme-cli" "nfs-utils" \
        "initscripts" "screen" "tmux" "git" "sshpass" "python-pip" "python3-pip" "lldpd" "bmon" \
        "nload" "pssh" "pdsh" "iperf" "fio" "htop" )

	red_hat_pkg_list_no=( "NetworkManager" )
	red_hat_pkg_list_no=( )
	for i in ${red_hat_pkg_list_weka[@]}; do
		rpm -q $i &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Package $i is REQUIRED for proper weka installation"
			ret="1" # FAIL
            install_needed="$install_needed $i"
		fi
	done
	if [ ! -d /etc/amazon ]; then	# Amazon does not use OFED
		for i in ${red_hat_pkg_list_ofed[@]}; do
			rpm -q $i &> /dev/null
			if [ $? -eq 1 ]; then
				write_log "Package $i is REQUIRED for proper OFED installation"
				ret="1" # FAIL
                install_needed="$install_needed $i"
			fi
		done
	fi
	for i in ${red_hat_pkg_list_general[@]}; do
		rpm -q $i &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Package $i is missing for RECOMMENDED installation for Weka runtime"
			ret="254"   # WARNING
            install_needed="$install_needed $i"
		fi
	done
	for i in ${red_hat_pkg_list_no[@]}; do
		rpm -q $i &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Package $i is installed but NOT RECOMMENDED for Weka runtime"
			ret="254" # WARNING
            remove_needed="$remove_needed $i"
		fi
	done

    needed_actions="${install_needed} ${remove_needed}"
    if [[ "$FIX" == "True" && "${needed_actions}" != "" ]]; then
        echo "--fix specified, attemping to install/remove packages"
        if [ "${install_needed}" != "" ]; then
            sudo yum -y install ${install_needed}
            if [ $? -ne 0 ]; then
                echo "Failure while installing packages."
                ret="1" # FAIL
            fi
        fi
        if [ "${remove_needed}" != "" ]; then
            sudo yum -y remove ${remove_needed}
            if [ $? -ne 0 ]; then
                echo "Failure while removing packages."
                ret="1" # FAIL
            fi
        fi
    fi

else
	write_log "Running on top of Debian based system (Ubuntu)"
	debian_pkg_list_weka=( "elfutils" "libelf-dev" "linux-libc-dev" "glibc-source" "make" "perl" "rpcbind" \
		"elfutils" )
	debian_pkg_list_ofed=( "pciutils" "gtk2" "atk" "cairo" "python-libxml2" "tcsh" "lsof" "tcl" "tk" )
	debian_pkg_list_general=( "net-tools" "wget" "sg3-utils" "gdisk" "ntpdate" "ipmitool" "sysstat" "strace" \
        "tcpdump" "telnet" "nmap" "hwloc" "numactl" "python3" "pciutils" "lsof" "wget" "bind-utils" "vim-enhanced" \
        "nvme-cli" "nfs-utils" "screen" "tmux" "git" "sshpass" "python-pip" "python3-pip" "lldpd" "bmon" "nload" \
        "pssh" "pdsh" "iperf" "fio" "htop" )
	debian_pkg_list_no=( "network-manager" )
	debian_pkg_list_no=( )
	for i in ${debian_pkg_list_weka[@]}; do
		dpkg -l | awk {'print $2'} | grep -i $i &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Package $i is missing for proper weka installation"
			ret="1" # FAIL
            install_needed="$install_needed $i"
		fi
	done
	for d in ${debian_pkg_list_ofed[@]}; do
		dpkg -l | awk {'print $2'} | grep -i $d &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Package $d is REQUIRED for proper OFED installation"
			ret="1" # FAIL
            install_needed="$install_needed $i"
		fi
	done
	for e in ${debian_pkg_list_general[@]}; do
		dpkg -l | awk {'print $2'} | grep -i $e &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Package $e is needed for RECOMMENDED installation for Weka runtime"
			ret="1" # FAIL
            install_needed="$install_needed $i"
		fi
	done
	for z in ${debian_pkg_list_no[@]}; do
		dpkg -l | awk {'print $2'} | grep -i $z &> /dev/null
		if [ $? -eq 1 ]; then
			write_log "Package $z is installed but NOT RECOMMENDED for Weka runtime"
			ret="1" # FAIL
            remove_needed="$remove_needed $i"
		fi
	done

    needed_actions="${install_needed} ${remove_needed}"
    if [[ "$FIX" == "True" && "${needed_actions}" != "" ]]; then
        echo "--fix specified, attemping to install/remove packages"
        if [ "${install_needed}" != "" ]; then
            sudo apt-get -y install ${install_needed}
            if [ $? -ne 0 ]; then
                echo "Failure while installing packages."
                ret="1" # FAIL
            fi
        fi
        if [ "${remove_needed}" != "" ]; then
            sudo apt-get -y remove ${remove_needed}
            if [ $? -ne 0 ]; then
                echo "Failure while removing packages."
                ret="1" # FAIL
            fi
        fi
    fi

fi
exit $ret
