#!/usr/bin/env bash
#
# Script to recommend client mount options to mount wekafs
#
# Written by Brady Turner brady.turner@weka.io
#
# set -x
#

#If number of parameters less than 1, give usage
if [ $# -lt 1 ]; then
        echo "Usage: $0 <hosts>"
        echo "where <hosts> is a space separated list of hosts or range x.x.x.{y..z} to check."
        exit
fi

# Check which interface goes to weka
echo -e "\nWhat is a DATA SERVING IP to connect to wekafs from this/these client(s)?:"
read WEKA_IP

NUM_HOSTS=0
for HOST in $*; do
        echo -e "\nChecking *** $HOST ***"
        let NUM_HOSTS=$NUM_HOSTS+1

        # Report interface
        NIC=`ssh $HOST ip route get to $WEKA_IP |awk '{print $3}'`
        PCI=`ssh $HOST lshw -class network -businfo | sed '1,2d' | awk '{printf("%s %s\n", substr($1,10,7),$2)}' |grep $NIC |awk '{print $1}'`
        echo -e "\nOk, that uses interface $PCI $NIC which has a NUMA region set to:\n "
        ssh $HOST lspci -vvv |grep -A 20 Mell |grep -A 20 $PCI |grep NUMA

        # check host NUMA setting
        echo -e "\nIt's NUMA region(s) are laid out: "
        ssh $HOST lscpu |grep NUMA

        # list core count
        echo -e "\nOn `ssh $HOST nproc --all` cores. "

        # ask which cores to use
        NUM_CORES=`ssh $HOST lspci -vvv |grep -A 20 Mell |grep -A 20 $PCI |grep NUMA |awk '{print $3}'`
        echo -e "\nWhich core(s) in NUMA node $NUM_CORES do you want to use for weka Frontend(s)? X [Y] [Z], etc."
        read -a CORES

        echo -e "\nYour recommended mount options are: \n"
        CORE_OPTION=`for i in "${CORES[@]}"; do echo -n "-o core=$i ";  done`
        echo -e "mount -t wekafs $CORE_OPTION-o net=$NIC <backend2>,$WEKA_IP/<fs> /mnt/<path>\n"

done
