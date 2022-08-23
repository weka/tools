#!/bin/bash
#run_once
    
# Globals
res="0"

function barline () {
## barline
echo "======================================================================"
}

function testname () {
## testname

echo "Test name: Testing Weka nodes physical RAM that is equal between hosts"
which hostname 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
        echo "Hostname command not found"
else
        echo "Hostname: `hostname`"
        echo "IP addresses: `hostname -I`"
fi
}

function testrun () {
# Test run
barline
testname

# Awk convert - echo num | awk '{ printf "%5.1f\n", $1 /1024/1024/1024 }'

rm -rf /tmp/gb.txt 1 >/dev/null 2> /dev/null
array_backends=( `weka cluster host -b | awk {'print $2'} | grep -vi 'id'` )
for t in ${array_backends[@]}; do
	weka cluster host info-hw | grep -i -A100 $t | grep -i "total:" | awk '{ printf "%5.1f\n", $2 /1024/1024/1024 }' >> /tmp/gb.txt
done
diff=`cat /tmp/gb.txt|uniq|wc -l`

if [ "$diff" != "1" ]; then 
	echo "At least one of the hosts has RAM incorrectly allocated"
	for t in ${array_backends[@]}; do
		echo "Host IP Adddress: `weka cluster host info-hw | grep -i -A69 $t | grep -i 'resolvedIp:' | awk '{ print $2 }'`"
		echo "Total RAM installed: `weka cluster host info-hw | grep -i -A63 $t | grep -i "total:" | awk '{ printf "%5.1f\n", $2 /1024/1024/1024 }'`GB of RAM"
	done
        res="1"
fi
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
