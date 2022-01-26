#!/bin/bash 
# Need to make sure we test all ip interfaces.

# Return codes are as follows: 0 = Success, >0 = Failure, 255 = Fatal failure (stop all tests)

DESCRIPTION="Run iperf to all nodes"
SCRIPT_TYPE="sequential"

ret="0"

# use awk for floating point math, because it's always installed.  bc is an alternative, but optional command
for i in $*; do
        # resolve the name, in case we have a name, not an ip addr
        TMP=`ping -c1 $i | head -1 | cut '-d ' -f3`
        TMP2=${TMP:1}
        IPADDR=${TMP2%")"}
	INTERFACE=`ip route get $IPADDR | awk '{ print $3 }'` 
	ISLOCAL=`ip route get $IPADDR | awk '{ print $1 }' | head -1` 
	if [ "$ISLOCAL" != "local" ]; then      #let's not talk to ourselves; pointless :)
		NETSPEED=`ethtool $INTERFACE | grep Speed | awk '{print $2}'`
		NETSPEED=${NETSPEED%Mb/s}
		NETGB=`echo $NETSPEED | awk '{ print $1 / 1000}'`
		GOOD=`echo $NETSPEED | awk '{ print $1 * 0.9}'`   # 90% of max is reasonable?
		echo "Link to $i is $NETSPEED Mbits/s or $NETGB Gbits/s"
		echo "starting iperf client to node $i"
		MBITS=`iperf -c $i -P 50 -f m | tail -1 | awk '{print $6}'`
		GBITS=`echo $MBITS | awk '{ print $1 / 1000}'`
		echo "node $i, $GBITS Gbits/s"
		if [ $MBITS -lt $GOOD ]; then		# can't do floating point in bash, but we can bypass that
			echo "Insufficient bandwidth to node $i detected"
			ret=1
		fi
	else
		echo "Skipping iperf to myself."
	fi
done

echo "iperfs complete!"

exit $ret
