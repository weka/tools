#!/bin/bash
#
 
#Globals
res="0"
get_deps="true"

function barline () {
## barline
echo "================================================================="
}

function testname () {
## testname

echo "Test name: Testing Weka backend server for ECC errors in RAM"
which hostname 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
        echo "Hostname command not found"
else
        echo "Hostname: `hostname`"
        echo "IP address: `hostname -I`"
fi
}

function check_ipmitool()
{
# Looking for ipmitool availability
which ipmitool 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
        echo "ipmitool not found"
        if [ "$get_deps" == "true" ]; then
                # Check if Debian based OS
                which lsb_release 1> /dev/null 2> /dev/null
                if [ $? -eq 0 ]; then
                        apt-get update 1> /dev/null 2> /dev/null
                        apt-get --yes install ipmitool 1> /dev/null > /dev/null
                        if [ $? -eq 1 ]; then
                                dpkg -i /tmp/lib/ipmitool_1.8.18-8_amd64.deb 1> /dev/null 2> /dev/null
                                if [ $? -eq 1 ]; then
                                        echo "Could not install ipmitool properly"
                                        res="1"
                                fi
                        fi
                else
                        yum install ipmitool -y 1> /dev/null 2> /dev/null
                        if [ $? -eq 1 ]; then
                                echo "Could not install ipmitool properly"
                                res="1"
                        fi
                fi
        else
                res="1"
        fi
fi
}

function check_ipmiutil()
{
# Looking for ipmitool availability
which ipmiutil 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
    echo "ipmiutil not found"
    if [ "$get_deps" == "true" ]; then
        # Check if Debian based OS
        which lsb_release 1> /dev/null 2> /dev/null
        if [ $? -eq 0 ]; then
                apt-get update 1> /dev/null 2> /dev/null
                apt-get --yes install ipmiutil 1> /dev/null 2> /dev/null
                if [ $? -eq 1 ]; then
                        dpkg -i /tmp/lib/ipmiutil_3.1.5-1_amd64.deb 1> /dev/null 2> /dev/null
                        if [ $? -eq 1 ]; then
                                echo "Could not install ipmiutil properly"
                                res="1"
                        fi
                fi
        else
                yum install ipmiutil -y 1> /dev/null 2> /dev/null
                if [ $? -eq 1 ]; then
                        rpm --quiet -i /tmp/lib/ipmiutil-3.1.6-1.1.x86_64.rpm 1> /dev/null 2> /dev/null
                        if [ $? -eq 1 ]; then
                                echo "Could not install ipmiutil properly"
                                res="1"
                        fi
                fi
        fi
    fi
fi

}

function check_dmidecode()
{
# Looking for IPMItool availability in the BIOS
which dmidecode 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
	echo "dmidecode tool not found"
	if [ "$get_deps" == "true" ]; then
		yum install dmidecode -y 1> /dev/null 2> /dev/null
		if [ $? -eq 1 ]; then
			echo "Could not install dmidecode properly"
			res="1"
		fi
	else
		res="1"
	fi
else
	dmidecode --type 38 | grep -i ipmi 1> /dev/null 2> /dev/null
	if [ $? -eq 1 ]; then
		echo "IPMI is not available on this system"
		res="1"
	fi
fi
}


function start_test()
{
# Starting ECC DIMM test
# Workaround for systems which could not install ipmiutil package properly
which ipmiutil 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
    which ipmitool 1> /dev/null 2> /dev/null
    if [ $? -eq 1 ]; then
        echo "Could not find ipmitool and ipmiutil binaries, IPMI tests could not be performed"
        res="1"
    else
        rm -rf /tmp/ipmitool_output.txt
        ipmitool sel elist > /tmp/ipmitool_output.txt
        cat /tmp/ipmitool_output.txt | grep -i "ecc" 1> /dev/null 2> /dev/null
        if [ $? -eq 0 ]; then
            cat /tmp/ipmitool_output.txt | grep -i "ecc" | tail -6
            res="1"
        fi
    fi
else
    rm -rf /tmp/ipmiutil_output.txt
    ipmiutil sel -e > /tmp/ipmiutil_output.txt
    cat /tmp/ipmiutil_output.txt |grep -i "bmc" |grep -i "asserted\|ecc" 1> /dev/null 2> /dev/null
    if [ $? -eq 0 ]; then
        cat /tmp/ipmiutil_output.txt |grep -i "bmc" |grep -i "asserted\|ecc" | tail -6
	    res="1"
    fi
fi

}



function start_test()
{
# Starting ECC DIMM test
rm -rf /tmp/ipmiutil_output.txt
ipmiutil sel -e > /tmp/ipmiutil_output.txt
cat /tmp/ipmiutil_output.txt |grep -i "bmc" |grep -i "asserted\|ecc" 1> /dev/null 2> /dev/null
if [ $? -eq 0 ]; then
	cat /tmp/ipmiutil_output.txt |grep -i "bmc" |grep -i "asserted\|ecc" | tail -6
	res="1"
fi

}

function testrun () {
# Test run
barline
testname
check_ipmitool
check_ipmiutil
check_dmidecode
start_test

}
# MAIN
# If there is parameter after the script run command, output everything out
if [ "$1" ]; then
        testrun
        if [ "$res" -eq "1" ]; then
                exit 1
        fi
else
        rm /tmp/$(basename $0).log 1> /dev/null 2> /dev/null
        testrun > /tmp/$(basename $0).log
        if [ "$res" -ne "0" ]; then
                cat /tmp/$(basename $0).log
                rm /tmp/$(basename $0).log 1> /dev/null 2> /dev/null
                exit 1
        else
                rm /tmp/$(basename $0).log 1> /dev/null 2> /dev/null
                exit 0
        fi
fi
