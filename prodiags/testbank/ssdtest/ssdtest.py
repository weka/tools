#!/bin/bash
# Test to verify Weka SSD drives operational parameters
# TODO:
# Walk through available backends with weka cluster drive
# 1. Get HostId: [0-9] 
# 2. Walk through each HostId and find unique (first occurance) of each SSD / NVME / Other drive 
# 3. Find mappings of drive to host (unique) 
# 4. With weka manhole get hardware notifications per drive, if failure per parameter, test failed for drive 
# 5. Test should run only once on first backend to fetch drives assigned (use #run_once) in test
# 6. Tested parameters: ACTIVE, Temperature note above 55.0C, endurance not below 95%
# This is a very long test, each drive tested about 2 seconds
# Set to run only once on system
#run_once

# Global testing status and consts
max_temperature="550" # in 550 = 55.0C
spares="95" # lowest spare for SSD endurance
spares_threshold="10" # statically set by system to 5

res="0"

function barline () {
## barline
echo "================================================================="
}

function testname () {
## testname

# Clean process
rm -rf /tmp/ssd_output_list.sh
rm -rf /tmp/ssd_compare.txt

echo "Test name: SSD / NVMe test"

which hostname 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
        echo "Hostname command not found"
else
        echo "Hostname: `hostname`"
        echo "IP address: `hostname -I`"
fi
}

function testrun () {
# Test run
barline
testname

weka cluster drive 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
	echo "Could not find weka executable"
	exit 1
fi

weka_version=`weka version | grep "* " | awk -F. {'print $1"."$2'} | sed 's/\*//g'`
if [ "$weka_version" == " 3.9" ]; then
    weka cluster drive | grep -i ' active' | awk {'print "echo ============================== ;\n echo NodeId: "$4" and DiskId: "$1" && weka debug manhole -J -n "$4" ssd_get_nvme_smart_log_page diskId="$1" \| grep \"percentage_used\\|readSuccess\\|available_spare\\|composite_temperature\\|critical_warning\\|errMsg\" \| sed '\''s/,//g'\'' \| sed '\''s/\"//g'\'' \| sed '\''s/^ *//g'\''"'} > /tmp/ssd_output_list.sh 2> /dev/null
elif [ "$weka_version" == " 3.10" ]; then
    weka cluster drive | grep -i ' active' | awk {'print "echo ============================== ;\n echo NodeId: "$4" and DiskId: "$1" && weka debug manhole -J -n "$4" ssd_get_nvme_smart_log_page diskId="$1" \| grep \"percentage_used\\|readSuccess\\|available_spare\\|composite_temperature\\|critical_warning\\|errMsg\" \| sed '\''s/,//g'\'' \| sed '\''s/\"//g'\'' \| sed '\''s/^ *//g'\''"'} > /tmp/ssd_output_list.sh 2> /dev/null
elif [ "$weka_version" == " 3.11" ]; then
    weka cluster drive | grep -i ' active' | awk {'print "echo ============================== ;\n echo NodeId: "$4" and DiskId: "$1" && weka debug manhole -J -n "$4" ssd_get_nvme_smart_log_page diskId="$1" \| grep \"percentage_used\\|readSuccess\\|available_spare\\|composite_temperature\\|critical_warning\\|errMsg\" \| sed '\''s/,//g'\'' \| sed '\''s/\"//g'\'' \| sed '\''s/^ *//g'\''"'} > /tmp/ssd_output_list.sh 2> /dev/null
elif [ "$weka_version" == " 3.12" ]; then
    weka cluster drive | grep -i ' active' | awk {'print "echo ============================== ;\n echo NodeId: "$4" and DiskId: "$1" && weka debug manhole -J -n "$4" ssd_get_nvme_smart_log_page diskId="$1" \| grep \"percentage_used\\|readSuccess\\|available_spare\\|composite_temperature\\|critical_warning\\|errMsg\" \| sed '\''s/,//g'\'' \| sed '\''s/\"//g'\'' \| sed '\''s/^ *//g'\''"'} > /tmp/ssd_output_list.sh 2> /dev/null
elif [ "$weka_version" == " 3.13" ]; then
    weka cluster drive | grep -i ' active' | awk {'print "echo ============================== ;\n echo NodeId: "$4" and DiskId: "$1" && weka debug manhole -J -n "$4" ssd_get_nvme_smart_log_page diskId="$1" \| grep \"percentage_used\\|readSuccess\\|available_spare\\|composite_temperature\\|critical_warning\\|errMsg\" \| sed '\''s/,//g'\'' \| sed '\''s/\"//g'\'' \| sed '\''s/^ *//g'\''"'} > /tmp/ssd_output_list.sh 2> /dev/null
elif [ "$weka_version" == " 3.14" ]; then
    weka cluster drive | grep -i ' active' | awk {'print "echo ============================== ;\n echo NodeId: "$4" and DiskId: "$1" && weka debug manhole -J -n "$4" ssd_get_nvme_smart_log_page diskId="$1" \| grep \"percentage_used\\|readSuccess\\|available_spare\\|composite_temperature\\|critical_warning\\|errMsg\" \| sed '\''s/,//g'\'' \| sed '\''s/\"//g'\'' \| sed '\''s/^ *//g'\''"'} > /tmp/ssd_output_list.sh 2> /dev/null
else # For version 3.8.1 or other than 3.9, 3.10, 3.11, 3.12, 3.13 and 3.14
    weka cluster drive | grep -i ' active' | awk {'print "echo ============================== ;\n echo NodeId: "$8" and DiskId: "$2" && weka debug manhole -J -n "$8" ssd_get_nvme_smart_log_page diskId="$2" \| grep \"percentage_used\\|readSuccess\\|available_spare\\|composite_temperature\\|critical_warning\\|errMsg\" \| sed '\''s/,//g'\'' \| sed '\''s/\"//g'\'' \| sed '\''s/^ *//g'\''"'} > /tmp/ssd_output_list.sh 2> /dev/null
fi

num_of_disks=`cat /tmp/ssd_output_list.sh | grep -v "=====" | wc -l`
echo "Number of media found: $num_of_disks disks"
sh /tmp/ssd_output_list.sh | tee /tmp/ssd_compare.txt

# Going through the ssd_compare_list, if error found output error with disk id and node id

iterations=`cat /tmp/ssd_compare.txt | grep -i diskid | wc -l`
for i in `seq $iterations`; do
	diskid=`grep -i diskid /tmp/ssd_compare.txt | head -$i | tail -1`
	errMsg=`grep -i errmsg /tmp/ssd_compare.txt | head -$i | tail -1`
	errMsg_res=`echo $errMsg | awk {'print $2'}`
	if [ "$errMsg_res" != "null" ]; then
		echo "Error message displaying : $errMsg_res for $diskid"
		res="1"
	fi
	readSuccess=`grep -i readsuccess /tmp/ssd_compare.txt | head -$i | tail -1`
	readSuccess_res=`echo $readSuccess | awk {'print $2'}`
	if [ "$readSuccess_res" != "true" ]; then
		echo "readSuccess parameter displaying : $readSuccess_res for $diskid"
		res="1"
	fi
	available_spare=`grep -i "available_spare:" /tmp/ssd_compare.txt | head -$i | tail -1`
	available_spare_res=`echo $available_spare | awk {'print $2'}`
	if [ $available_spare_res -le $spares ]; then
		echo "available_spare parameter displaying : $available_spare_res for $diskid"
		res="1"
	fi
	available_spare_threshold=`grep -i "available_spare_threshold" /tmp/ssd_compare.txt | head -$i | tail -1`
	available_spare_threshold_res=`echo $available_spare_threshold | awk {'print $2'}`
	if [ $available_spare_threshold_res -gt $spares_threshold ]; then
		echo "available_spare_threshold parameter displaying : $available_spare_threshold_res for $diskid"
		res="1"
	fi
	composite_temperature=`grep -i "composite_temperature:" /tmp/ssd_compare.txt | head -$i | tail -1`
	composite_temperature_res=`echo $composite_temperature | awk {'print $2'}`
	if [ $composite_temperature_res -gt $max_temperature ]; then
		echo "composite_temperature parameter displaying : $composite_temperature_res for $diskid"
		res="1"
	fi
	critical_composite_temperature_time=`grep -i "critical_composite_temperature_time:" /tmp/ssd_compare.txt | head -$i | tail -1`
	critical_composite_temperature_time_res=`echo $critical_composite_temperature_time | awk {'print $2'}`
	if [ $critical_composite_temperature_time_res -gt 0 ]; then
		echo "critical_composite_temperature_time parameter displaying : $critical_composite_temperature_time_res for $diskid"
		res="1"
	fi
	critical_warning=`grep -i "critical_warning:" /tmp/ssd_compare.txt | head -$i | tail -1`
	critical_warning_res=`echo $critical_warning | awk {'print $2'}`
	if [ $critical_warning_res -gt 0 ]; then
		echo "critical_warning parameter displaying : $critical_warning_res for $diskid"
		res="1"
	fi
	warning_composite_temperature_time=`grep -i "warning_composite_temperature_time:" /tmp/ssd_compare.txt | head -$i | tail -1`
	warning_composite_temperature_time_res=`echo $warning_composite_temperature_time | awk {'print $2'}`
	if [ $warning_composite_temperature_time_res -gt 0 ]; then
		echo "warning_composite_temperature_time parameter displaying : $warning_composite_temperature_time_res for $diskid"
		res="1"
	fi
done
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

