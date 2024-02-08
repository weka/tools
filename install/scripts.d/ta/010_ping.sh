#!/bin/bash

DESCRIPTION="Dataplane IP Jumbo Frames/Routing test"
# script type is single, parallel, or sequential
SCRIPT_TYPE="single"

# Put your stuff here
ret="1"

which ping &> /dev/null
if [ $? -eq 1 ]; then
	if [[ $ID_LIKE == *debian* ]]; then
		PACKAGE="iputils-ping"
	elif [[ $ID_LIKE == *rhel* ]]; then
		PACKAGE="iputils"
	fi
	echo "ping not found." 
	if [ "$FIX" == "True" ]; then
		echo "Fix requested. Installing ping"
		if [[ $ID_LIKE == *debian* ]]; then
			sudo apt-get update
			sudo apt-get -y install iputils-ping
		elif [[ $ID_LIKE == *rhel* ]]; then
			sudo yum -y install iputils
		fi
	else
		echo "Please install $PACKAGE or use --fix option"
		exit "255" 
	fi
fi

let PINGERRORS=0
let JUMBOERRORS=0
let ROUTEWARNS=0
let LOCALMTUERRORS=0
let LINKTYPEERRORS=0
IFLAST="none"
IFHW=""
PASSED=()
#
# check ssh connectivity, if given hostnames/ips on command line
#
if [ $# -gt 0 ]; then
	echo Running from `hostname`
	for i in $*
	do
	  # resolve the name, in case we have a name, not an ip addr
	  QUICKPING=`ping -c1 $i`
	  if [ $? -gt 0 ]; then
	      PINGERRORS=$PINGERRORS+1
		  echo "   *FAIL: Unable to ping $i"
		  echo "        $QUICKPING"
		  exit "255"
	  fi
      IPRESOLVED=`ping -c1 $i | head -1 | cut '-d ' -f3`
      DESTIPADDR=${IPRESOLVED:1:-1}
	  # using sed below because the output of the 'ip' command isn't strictly columnar; data may be in different columns
	  # determine which interface will be used to get to this address
	  IFS=' ';RT=(`ip -o route get $DESTIPADDR`)
	  IF=`echo ${RT[*]} | grep -oP "dev \K\S*"`
	  SRC=`echo ${RT[*]} | grep -oP "src \K\S*"`
	  VIA=`echo ${RT[*]} | grep -oP "via \K\S*"`
	  if [ $IF != $IFLAST ]; then IFLAST=$IF; IFHW=""; fi
	  DEVINFO=`ip -o link show dev $IF`
	  LINKTYPE=`echo $DEVINFO | grep -oE "(ether|infiniband|loopback)"` # link type
	  CONF_MTU=`echo $DEVINFO | grep -oP "mtu \K[0-9]*"` # extract mtu 

	  # LINK should now be either "ether" or "infiniband" or "loopback"
	  if [ "$LINKTYPE" == "loopback" ]; then continue; fi
      if [ "$LINKTYPE" == "ether" ]; then 
	    MTU="9000"; PINGMTU="8972"
      elif [ "$LINKTYPE" == "infiniband" ]; then
	    MTU="4092"; PINGMTU="4064"
      else
        echo "Unknown link type $LINKTYPE when determining target MTU - $DEVINFO"
	    if [ -z "$IFHW" ]; then IFHW=`lshw -class network -short  2> /dev/null | grep $IF`; fi
		IFHWA=($IFHW)
		echo "             $IF hardware: \"${IFHWA[@]:3}\""
	    let LINKTYPEERRORS=$LINKTYPEERRORS+1
		continue
      fi
	  if [ ! -z "$VIA" ]; then
	  	echo "    WARN: `hostname` to $DESTIPADDR routes via gateway $VIA from dev $IF (src ip $SRC)"
		if [ $ROUTEWARNS -eq 0 ]; then
			echo "           Is $IF a dataplane interface?  Is routed dataplane path intentional? "
	    	if [ -z "$IFHW" ]; then IFHW=`lshw -class network -short  2> /dev/null | grep $IF`; fi
			IFHWA=($IFHW)
			echo "             $IF hardware: \"${IFHWA[@]:3}\""
		fi
		let ROUTEWARNS=$ROUTEWARNS+1
	  fi
 
      if [ "$CONF_MTU" != "$MTU" ]; then
			let LOCALMTUERRORS=$LOCALMTUERRORS+1
        	echo "   *FAIL: `hostname` interface $IF MTU is $CONF_MTU not $MTU (type '$LINKTYPE', src: $SRC, dest: $DESTIPADDR)"
	    	if [ -z "$IFHW" ]; then 
				IFHW=`lshw -class network -short 2> /dev/null | grep $IF`; 
				echo "          Is $IF a dataplane interface?"
				IFHWA=($IFHW)
				echo "             $IF hardware: \"${IFHWA[@]:3}\""
			fi
			continue
      fi
	  # check for jumbo frames working correctly as well as basic connectivity.
	  sudo ping -M 'do' -c 2 -i 0.2 -s $PINGMTU  $i &> /dev/null
	  if [ ! $? -eq 0 ]; then	# change to not eq 0
		echo $PINGOUT
		echo "   *FAIL: Host $i JUMBO FRAME packet test error over $IF."
		let JUMBOERRORS=$JUMBOERRORS+1
	    if [ -z "$IFHW" ]; then IFHW=`lshw -class network -short 2> /dev/null | grep $IF`; fi
		echo "          MTU set properly on $IF - check for incorrect MTU on entire path from $SRC to $DESTIPADDR"
		IFHWA=($IFHW)
		echo "             $IF hardware: \"${IFHWA[@]:3}\""
	  else
	    PASSED+=("      OK: `hostname` (interface $IF, ip $SRC) to $DESTIPADDR")
	  fi
	done
else
	echo "No hosts specified, skipping ping/jumbo frame connectivity test."
fi

for m in "${PASSED[@]}"; do
    echo "$m"
done

if [ $PINGERRORS -gt 0 ]; then
    echo "$PINGERRORS hosts unreachable; aborting tests"
	exit "255"
fi
if [ $JUMBOERRORS -gt 0 ] || [ $LOCALMTUERRORS -gt 0 ] || [ $LINKTYPEERRORS -gt 0 ]; then
    let E=$JUMBOERRORS+$LOCALMTUERRORS+$LINKTYPEERRORS
#    echo "    ($E jumbo ping errors)"
	exit "1" # jumbo frames not enabled/working on all, so error, not warn
fi

if [ $ROUTEWARNS -gt 0 ]; then
	exit "254"		
fi
echo "All tests passed."
exit "0"
