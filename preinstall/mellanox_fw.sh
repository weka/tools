#!/usr/bin/env bash
#
# Script to upgrade/install Mellanox MFT tools/driver firmware and set preferred PCI settings for max performance
#
# Assumptions:
#       OFED installed
#       Internet access for MFT/driver toolsets
#       CHECK MFT and MLX variables at the beginning are the latest!!!
#
# Written by Brady Turner brady.turner@weka.io
# Report bugs or enhancement requests to https://github.com/weka/tools/issues
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
        echo -e "\n*** Checking $HOST ***\n"
        let NUM_HOSTS=$NUM_HOSTS+1

        # check if MFT is already installed on this host
        ssh $HOST which mst > /dev/null 2>&1
        if [ $? -eq 0 ]; then
                echo -e "MFT version for host $HOST is:\n "
                ssh $HOST mst start > /dev/null 2>&1
                ssh $HOST mst version |awk '{print $3}' |rev |cut -c2- |rev
                echo -e "\nWould you like to upgrade the Mellanox firmare management/debug toolset to `basename $MFT?` (yn): "
                read ANS
                if [ "$ANS" = "n" ]; then
                        echo -e "\nNext!"
                        #continue
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

        echo -e "\nNow let's check your MLNX driver versions:\n "
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
                                for i in `ssh $HOST ls /dev/mst/mt4123*f[0-1]`; do ssh $HOST /tmp/mlxup -d $i; done
                        else
                            :
                        fi
                fi

        echo "Do you want want to update the MLNX settings for max performance? (yn): "
        read ANS

            if [ "$ANS" != "y" ]; then
                :
        else
            ssh $HOST 'hostname; for i in `ls /dev/mst/mt4123*`; do mlxconfig -y -d $i s ADVANCED_PCI_SETTINGS=1 PCI_WR_ORDERING=1; done'
            echo -e "\nSettings ADVANCED_PCI_SETTINGS and PCI_WR_ORDERING set to 1 for 30% perf gain!:\n "
            ssh $HOST 'hostname; for i in `ls /dev/mst/mt4123*`; do ls $i; mlxconfig -d $i q |grep -e ADVANCED_PCI_SETTINGS -e PCI_WR_ORDERING; done'

        fi

        echo "Done! Reboot $HOST now for any changes to take effect? (yn): "
        read ANS
            if [ "$ANS" != "y" ]; then
            :
        else
            echo "Rebooting host $HOST now"
            ssh $HOST "sleep 2; shutdown -r now"&
        fi

done

echo -e "\nAll done!  BYE!"
