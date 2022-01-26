#! /bin/bash
echo '=== Weka Version ==='
weka version current
echo '=== Mount Options  ==='
mount | grep wekafs
echo '=== Weka Config ==='
weka status
weka cluster host
weka cluster drive
weka cluster host net
weka cluster nodes
weka cluster buckets
weka fs
echo '=== Linux Page Cache  ==='
sudo sysctl vm.dirty_background_bytes
sudo sysctl vm.dirty_background_ratio
sudo sysctl vm.dirty_bytes
sudo sysctl vm.dirty_expire_centisecs
sudo sysctl vm.dirty_ratio
sudo sysctl vm.dirty_writeback_centisecs
sudo sysctl vm.dirtytime_expire_seconds
echo '=== RA ==='
for i in `ls /sys/class/bdi/ | grep weka`; do cat /sys/class/bdi/$i/read_ahead_kb; done
echo '=== host ==='
sudo lscpu
sudo free
sudo uname -a
echo '=== IB Network ==='
linklayer=`weka status | grep "link layer:" | awk -F: '{print $2}'`
if [ $linklayer == "InfiniBand" ]; then ibnetdiscover; fi 
echo '=== Weka Config Dump ==='
sudo weka local run -- /weka/cfgdump
