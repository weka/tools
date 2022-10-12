#!/usr/bin/env bash
#
# Script to upgrade/install Mellanox MFT tools/driver firmware and set preferred PCI settings for max performance
#
# Assumptions:
#       OFED installed
#       Internet access for MFT/driver toolsets
#       Run on first cluster host if range is given
#       MFT and MLX variables at top here set to latest
#
# Written by Brady Turner brady.turner@weka.io
#
# set -x
#

# EDIT below location for latest MFT tool. Check https://network.nvidia.com/products/adapter-software/firmware-tools/
MFT=https://www.mellanox.com/downloads/MFT/mft-4.21.0-99-x86_64-rpm.tgz

# EDIT below location for latest mlxup tool for firmware updates. Check https://network.nvidia.com/support/firmware/mlxup-mft/
MLX=https://www.mellanox.com/downloads/firmware/mlxup/4.21.0/SFX/linux_x64/mlxup

#If number of parameters less than 1, give usage
if [ $# -lt 1 ]; then
        echo "Usage: $0 <hosts>"
        echo "where <hosts> is a space separated list of hosts or range x.x.x.{y..z} to deploy to."
        exit
fi

NUM_HOSTS=0
for HOST in $*; do
        echo "Checking $HOST"
        let NUM_HOSTS=$NUM_HOSTS+1

        # check if MFT is already installed on this host
        ssh $HOST which mst > /dev/null 2>&1
        if [ $? -eq 0 ]; then
                echo "MFT version for host $HOST is: "
                ssh $HOST mst start > /dev/null 2>&1
                ssh $HOST mst version
                echo -n "Would you like to upgrade it to $MFT? (yn): "
                read ANS
                if [ "$ANS" = "n" ]; then
                        echo "Next!"
                        continue
                else
                        ssh $HOST "cd /tmp; wget $MFT &> /dev/null"
                        ssh $HOST yum install -y libelf-dev libelf-devel elfutils-libelf-devel > /dev/null 2>&1
                        ssh $HOST apt-get -y install -y libelf-dev libelf-devel elfutils-libelf-devel > /dev/null 2>&1
                        ssh $HOST "cd /tmp; tar -xvf mft*.tgz; cd mft-*rpm; sudo ./install.sh > /dev/null 2>&1"
                        echo "Starting mst on host $HOST"
                        ssh $HOST mst start > /dev/null 2>&1; mst version
                fi

        else
                ssh $HOST ofed_info > /dev/null 2>&1
                if [ $? -ne 0 ]; then
                        echo "OFED not installed on $HOST. Please install and re-run."
                        echo "Your OS and architecture is: "
                        ssh $HOST egrep '^(VERSION|NAME)=' /etc/os-release; uname -m
                        exit
                else
                        echo -n "MFT is not installed on host $HOST. Would you like to install $MFT? (yn): "
                        read ANS
                        if [ "$ANS" = "n" ]; then
                                echo "MFT must be installed to continue.  Bye!"
                        exit
                        else
                                echo $HOST
                                ssh $HOST "cd /tmp; wget $MFT &> /dev/null"
                                ssh $HOST "cd /tmp; tar -xvf mft*.tgz; cd /tmp/mft-*rpm; sudo ./install.sh > /dev/null 2>&1"
                                echo "Starting mst on host $HOST"
                                ssh $HOST "mst start > /dev/null 2>&1; mst version"
                        fi
                fi
        fi
done

echo "Now let's check your MLNX driver versions: "
NUM_HOSTS=0
for HOST in $*; do
        ssh $HOST ofed_info > /dev/null 2>&1
                if [ $? -eq 1 ]; then
                        echo "OFED not installed on $HOST! Please install before continuing. Bye!"
                        exit
                else
                        ssh $HOST hostname; ibv_devinfo |grep -e fw_ver -e hca_id
                        echo "Would you like to check for newer version(s)? (yn): "
                        read ANS
                        if [ "$ANS" = "y" ]; then
                                ssh $HOST "cd /tmp; wget $MLX &> /dev/null; chmod +x /tmp/mlxup; "
                                for i in `ssh $HOST ls /dev/mst/mt4123*`; do ssh $HOST /tmp/mlxup -d $i; done
                        else
                                continue
                        fi
                fi
done

echo "Do you want want to update the MLNX settings for max performance? (yn): "
read ANS
if [ "$ANS" != "y" ]; then
    :
else
    NUM_HOSTS=0
    for HOST in $*; do
        let NUM_HOSTS=NUM_HOSTS+1
                ssh $HOST 'hostname; for i in `ls /dev/mst/mt41*f[0-1]`; do mlxconfig -y -d $i s ADVANCED_PCI_SETTINGS=1 PCI_WR_ORDERING=1; done'
        echo -e "\n Settings ADVANCED_PCI_SETTINGS and PCI_WR_ORDERING set to 1 for 30% perf gain!: "
                ssh $HOST 'hostname; for i in `ls /dev/mst/mt41*f[0-1]`; do ls $i; mlxconfig -d $i q |grep -e ADVANCED_PCI_SETTINGS -e PCI_WR_ORDERING; done'
   done
fi

echo "Done! Reboot cluster now for the changes to take effect? (yn): "
read ANS
if [ "$ANS" != "y" ]; then
    exit
else
        NUM_HOSTS=0
        for HOST in $*; do
        let NUM_HOSTS=NUM_HOSTS+1
                echo "Rebooting host $HOST now"
                ssh $HOST "sleep 2; shutdown -r now"&
        done
fi

exit
