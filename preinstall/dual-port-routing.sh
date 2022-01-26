#!/usr/bin/env bash 

#
# Set up dual-ported routes
#

errmsg()
{
    echo $* >&2
} # errmsg

network_spec()
{
    # input arg is a ip addr spec in the form ipaddr/maskbits - X.X.X.X/nn
    # returns network number spec in the form X.X.X.X/nn

    #IP=`echo $1 | awk -F/ '{print $1}'`
    #MASKBITS=`echo $1 | awk -F/ '{print $2}'`

    # sorry, but this is way easier in Python...
    python3 -c '
import argparse

# Parse arguments
parser = argparse.ArgumentParser(description="get ip information")
parser.add_argument("ipaddr_spec", metavar="ipaddr_spec", type=str )
args = parser.parse_args()

def ip_to_int( ipaddr_str ):
    parts = ipaddr_str.split( "." )
    return (int( parts[0] ) << 24) + (int( parts[1] ) << 16) + (int( parts[2] ) << 8) + int( parts[3] )

def int_to_ip( ipaddr_int ):
    return str( ipaddr_int >> 24 ) + "." + str( (ipaddr_int & (255 << 16)) >> 16) + "." + str( (ipaddr_int & (255 << 8)) >> 8 ) + "."  + str( ipaddr_int & 255 )

def network_ip( ipaddr, maskbits ):
    int_ipaddr = ip_to_int( ipaddr )
    mask = (int( "0xffffffff", 16 ) >> (32-int(maskbits))) << (32-int(maskbits))
    return int_to_ip( int_ipaddr & mask )

ip_info = args.ipaddr_spec.split( "/" )

# ip_info[0] is the ip addr, and ip_info[1] is the netmask bits
print( network_ip( ip_info[0], ip_info[1] ) + "/" + ip_info[1] )
    ' $1

} # network_spec


validate_nic()
{

    # Validate NICs
    ip a | grep $1: &> /dev/null
    if [ $? != 0 ]; then
        errmsg "Error: Network interface $1 not found"
        return 1
    fi

    ethtool $1 &> /dev/null
    if [ $? != 0 ]; then
        errmsg "Error: Network interface $1 not found"
        return 1
    fi

    if [ `ethtool $1 | grep "Link detected:" | cut -d: -f2` != "yes" ]; then
        errmsg "Error: Network interface $1 offline"
        return 1
    fi

    INET=`ip address show dev $1 | grep "inet "`
    if [ $? != 0 ]; then
        errmsg "Error: Interface $1 has no ip address"
        return 1
    fi

    echo "$INET" | awk '{print $2}'

    return 0
} # validate_nic


###################################################
# Main
###################################################
NET_SCRIPTS=/etc/sysconfig/network-scripts

if [ $# -ne 2 ]; then
    echo "Usage: $0 nic_interface1 nic_interface2"
    echo "or: $0 nic_interface1/gateway1 nic_interface2/gateway2"
    echo "    example: $0 enp59s0f0 enp79s0f0"
    echo "    optionally: $0 enp59s0f0/10.20.20.254 enp79s0f0/10.20.20.254"
    exit 1
else
    NIC1=`echo $1 | awk -F/ '{ print $1 }'`
    GATEWAY1=`echo $1 | awk -F/ '{ print $2 }'`
    NIC2=`echo $2 | awk -F/ '{ print $1 }'`
    GATEWAY2=`echo $2 | awk -F/ '{ print $2 }'`
fi

# check that the nic given are sane and fetch address info - X.X.X.X/nn
NIC1_IP_SPEC=`validate_nic $NIC1`
if [ $? != 0 ]; then
    exit 1
fi
NIC2_IP_SPEC=`validate_nic $NIC2`
if [ $? != 0 ]; then
    exit 1
fi


# gather some details that we'll need
NIC1_NET=`network_spec $NIC1_IP_SPEC`    # network number
NIC2_NET=`network_spec $NIC2_IP_SPEC`

NIC1_IP=`echo $NIC1_IP_SPEC | awk -F/ '{print $1}'`  # ip addr X.X.X.X
NIC2_IP=`echo $NIC2_IP_SPEC | awk -F/ '{print $1}'`

#echo "NIC1's IP: $NIC1_IP"
#echo "NIC2's IP: $NIC2_IP"

if [ "$NIC1_NET" != "$NIC2_NET" ]; then
    errmsg "The two interfaces specified are not on the same network"
    exit
fi

# unit test
#exit

# check for route scripts
echo "Setting Route Scripts for $NIC1"
if [ -f $NET_SCRIPTS/route-$NIC1 ]; then
    errmsg "$NET_SCRIPTS/route-$NIC1 already exists.  Skipping"
else
    echo "$NIC1_NET dev $NIC1 src $NIC1_IP table weka1" > $NET_SCRIPTS/route-$NIC1
    if [ "$GATEWAY1" != "" ]; then
        echo "default via $GATEWAY1 dev $NIC1 table weka1" >> $NET_SCRIPTS/route-$NIC1
    fi
fi

echo "Setting Route Scripts for $NIC2"
if [ -f $NET_SCRIPTS/route-$NIC2 ]; then
    errmsg "$NET_SCRIPTS/route-$NIC2 already exists.  Skipping"
else
    echo "$NIC2_NET dev $NIC2 src $NIC2_IP table weka2" > $NET_SCRIPTS/route-$NIC2
    if [ "$GATEWAY2" != "" ]; then
        echo "default via $GATEWAY2 dev $NIC2 table weka2" >> $NET_SCRIPTS/route-$NIC2
    fi
fi

# check for rule scripts
echo "Setting Rule Scripts for $NIC1"
if [ -f $NET_SCRIPTS/rule-$NIC1 ]; then
    errmsg "$NET_SCRIPTS/rule-$NIC1 already exists.  Skipping"
else
    echo "table weka1 from $NIC1_IP" > $NET_SCRIPTS/rule-$NIC1
fi

echo "Setting Rule Scripts for $NIC2"
if [ -f $NET_SCRIPTS/rule-$NIC2 ]; then
    errmsg "$NET_SCRIPTS/rule-$NIC2 already exists.  Skipping"
else
    echo "table weka2 from $NIC2_IP" > $NET_SCRIPTS/rule-$NIC2
fi


# check rt_tables
echo "Setting Route Tables"
grep weka1 /etc/iproute2/rt_tables &> /dev/null
if [ $? != 1 ]; then
    errmsg "/etc/iproute2/rt_tables seems to already have weka entries"
else
    echo "100 weka1" >> /etc/iproute2/rt_tables
    echo "101 weka2" >> /etc/iproute2/rt_tables
fi

# check if entries are in /etc/sysctl.conf, if not, put them there.
echo "Setting arp in sysctl.conf"
grep ^net.ipv4.conf.all.arp_filter /etc/sysctl.conf &> /dev/null
if [ $? != 0 ]; then
    errmsg "Making entries in /etc/sysctl.conf"
    (
    echo "net.ipv4.conf.all.arp_filter = 1"
    echo "net.ipv4.conf.default.arp_filter = 1"
    echo "net.ipv4.conf.all.arp_announce = 2"
    echo "net.ipv4.conf.default.arp_announce = 2"
    ) >> /etc/sysctl.conf
    sysctl -p /etc/sysctl.conf
else
    errmsg "Entries exist in /etc/sysctl.conf"
fi

