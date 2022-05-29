#!/usr/bin/env bash

#version=1.11

# Colors
export NOCOLOR="\033[0m"
export CYAN="\033[0;36m"
export YELLOW="\033[1;33m"
export RED="\033[0;31m"
export GREEN="\033[1;32m"
export BLUE="\033[1;34m"

DIR='/tmp'
SSH='/usr/bin/ssh'
LOG="$DIR/core.log"
FILE="$DIR/update_core_config.py"
CLIENTHOST="$DIR/weka_client_host.txt"
BACKENDIP=$(weka cluster host -b --no-header -o ips,status | awk '/UP/ {print $1}' | tr -d ',')
WEKACLIENT=$(weka cluster host -c --no-header -o id,hostname,ips,status | awk '/UP/ {print $1}')
CURRHOST=$(weka local resources | awk '/Management/ {print $3}')
CSLEEP=120
BSLEEP=60

weka cluster host -c --no-header -o hostname,status | awk '/UP/ {print $1}' > $CLIENTHOST

usage()
{
cat <<EOF
Usage: [-t To specify the total number of cores to be allocated to Weka must not exceed 19]
Usage: [-d To specify the total number of drive cores to be allocated to Weka]
Usage: [-f To specify the total number of frontend cores to be allocated to Weka]
Usage: [-c Number of client hosts to be blacklisted at a time, should be greater than 2. If you want to skip client blacklisting use -c 0]
Usage: [-b To perform core allocation changes on a single host]
Usage: [-s Timeout in seconds between client blacklisting, default value 120 seconds]
Usage: [-S Timeout in seconds between backend blacklisting and core relloaction, default value 60 seconds]
Usage: [-l Skip blacklist of backend hosts.]
This script allow the reallocation of cores designated to Weka. Prior to core re-allocation all backend hosts and client hosts must go through a blacklist process this ensures that there are no partially connected nodes.
OPTIONS:
  -t  Assign number of Total cores.
  -d  Assign number of Drive cores.
  -f  Assign number of Frontend cores.
  -c  Number for client hosts to blacklist at a time.
  -b  perform actions on a single host
  -s  Timeout in seconds between client blacklisting.
  -S  Timeout in seconds between backend blacklisting and core relloaction.
  -l  Skip blacklist of backend hosts.
EOF
exit
}

while getopts ":t:d:f:c:b:s:S:l:" o; do
    case "${o}" in
        t)
            TOTALC=${OPTARG}
            [[ $TOTALC -gt "19" ]] && usage
            ;;
        d)
            DRIVE=${OPTARG}
            ;;
        f)
            FRONT=${OPTARG}
            ;;
        c)
            NC=${OPTARG}
            ;;
        b)
            BACKEND=${OPTARG}
            ;;
        s)
            CSLEEP=${OPTARG}
            ;;
        S)
            BSLEEP=${OPTARG}
            ;;
        l)
            BKLIST=${OPTARG}
            ;;
        :)
            echo "ERROR: Option -$OPTARG requires an argument"
            usage
            ;;
        \?)
            echo "ERROR: Invalid option -$OPTARG"
            usage
            ;;
    esac
done

shift $((OPTIND -1))

if [ -z "${TOTALC}" ] || [ -z "${DRIVE}" ] || [ -z "${FRONT}" ] || [ -z "${NC}" ]; then
    usage
fi

if [ ! -z "$BACKEND" ]; then
  if ! [[ $BACKEND =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
  BAD "Must enter a valid ip address, cannot continue."
    exit 1
  fi
fi

function _sleep() {
    local SLEEP=$1
    for ii in $(seq "${SLEEP}" -1 1)
    do
        sleep 1
        printf ${CYAN}"\r%-28s" " Sleeping for $ii seconds ..."
    done
    printf "\r%-28s" " "
}

function logit() {
  echo -e "[${USER}][$(date)] - ${*}\n" >> ${LOG}
}

function LogRotate () {
local f="$1"
local limit="$2"
# Deletes old log file
  if [ -f "$f" ]; then
    CNT=${limit}
    let P_CNT=CNT-1
  if [ -f "${f}"."${limit}" ]; then
    rm "${f}"."${limit}"
  fi

# Renames logs .1 trough .3
while [[ $CNT -ne 1 ]] ; do
  if [ -f "${f}"."${P_CNT}" ]; then
    mv "${f}"."${P_CNT}" "${f}"."${CNT}"
  fi
  let CNT=CNT-1
  let P_CNT=P_CNT-1
done

# Renames current log to .1
mv "$f" "${f}".1
echo "" > "$f"
fi
}

function NOTICE() {
echo -e "\n${CYAN}$1${NOCOLOR}"
logit "${CYAN}""[$1]""${NOCOLOR}"
}

function GOOD() {
echo -e "${GREEN}$1${NOCOLOR}"
logit "${GREEN}"[ SUCCESS ] "$1" "${NOCOLOR}"
}

function WARN() {
echo -e "${YELLOW}$1${NOCOLOR}"
logit "${YELLOW}"[ WARN ] "$1" "${NOCOLOR}"
}

function BAD() {
echo -e "${RED}$1${NOCOLOR}"
logit "${RED}"[ FAILED ] "$1" "${NOCOLOR}"
}

NOTICE "VERIFYING WEKA AGENT"
WEKAVERIFY=$(lsmod | grep -i weka)
if [ -z "$WEKAVERIFY" ]; then
  BAD "Weka is NOT installed on host or the container is down, cannot continue."
  exit 1
fi

NOTICE "VERIFYING WEKA VERSION"
  MAJOR=$(weka version current | cut -d "." -f1)
  WEKAMINOR1=$(weka version current | cut -d "." -f2)
if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -ge 11 ]]; then
  GOOD "Supported Weka version"
fi

NOTICE "WEKA USER LOGIN TEST"
WEKALOGIN=$(weka cluster nodes 2>&1 | awk '/error:/ {print $1}')
if [ "$WEKALOGIN" == "error:" ]; then
  BAD "Please login using weka user login first, cannot continue."
  exit 1
else
  GOOD "Weka user login successful."
fi

NOTICE "WEKA IDENTIFIED"
CLUSTER=$(weka status | grep cluster | awk 'NR==1 {print $2}')
UUID=$(weka status | grep cluster | awk 'NR==1 {print $3}')
CLUSTERSTATUS=$(weka status | grep status | head -n -1 | cut -d':' -f2)
IOSTATUS=$(weka status | grep status | tail -n +2 | cut -d':' -f2)
GOOD "Working on CLUSTER: $CLUSTER UUID: $UUID STATUS:${CLUSTERSTATUS}${IOSTATUS}."

#verify local container status otherwise commands will fail
NOTICE "VERIFYING WEKA LOCAL CONTAINER STATUS"
CONSTATUS=$(weka local ps --no-header -o name,running | grep -i default | awk '{print $2}')
if [ "$CONSTATUS" == "False" ]; then
  BAD "Weka local container is down cannot continue."
  exit
else
  GOOD "Weka local container is running."
fi

NOTICE "CHECKING FOR ANY ALERTS"
WEKAALERTS="$(weka status | awk '/alerts:/ {print $2}')"
if [ "$WEKAALERTS" != 0 ]; then
  WARN "$WEKAALERTS Weka alerts present, for additional details see log ${LOG}."
  logit "\n$(weka alerts)"
else
  GOOD "No Weka alerts present."
fi

NOTICE "CHECKING REBUILD STATUS"
REBUILDSTATUS=$(weka status rebuild -J | awk '/progressPercent/ {print $2}' | tr -d ',')
if [ "$REBUILDSTATUS" = 0 ]; then
  GOOD "No rebuild in progress."
else
  WARN "Rebuild in progress, will continue after it's complete."
  while : ; do
    REBUILDSTATUS="$(weka status rebuild -J | awk '/progressPercent/ {print $2}' | tr -d ',')"
    echo -ne "$REBUILDSTATUS%\\r"
    if [ "$REBUILDSTATUS" = 0 ]; then
      GOOD "Rebuild complete, continuing."
      break
    fi
  done
fi

NOTICE "VERIFYING WEKA BACKEND HOST STATUS"
WEKAHOST=$(weka cluster host --no-header -o id,hostname,status -b | grep -v UP)
if [ -z "$WEKAHOST" ]; then
  GOOD "Verified all backend host's are UP."
else
  WEKAHOST=$(weka cluster host -o id,hostname,status -b | grep -v UP)
  BAD "Failed backend hosts detected."
  WARN "\n$WEKAHOST\n"
fi

NOTICE "VERIFYING WEKA CLIENT(S) STATUS"
WEKACLIENT=$(weka cluster host --no-header -c | grep -v UP)
if [ -z "$WEKACLIENT" ]; then
  GOOD "Verified all client's are up."
else
  WEKACLIENT=$(weka cluster host -o id,hostname,status -c | grep -v UP)
  BAD "Failed WEKA clients detected."
  WARN "\n$WEKACLIENT\n"
fi

NOTICE "VERIFYING WEKA NODES STATUS"
WEKANODES=$(weka cluster nodes --no-header | grep -v UP)
if [ -z "$WEKANODES" ]; then
  GOOD "Weka Nodes Status OK."
else
  WEKANODES=$(weka cluster nodes -o host,ips,status,role | grep -v UP)
  BAD "Failed Weka Nodes Found."
  WARN "\n$WEKANODES\n"
fi

let SSHERRORS=0
NOTICE "SSH connectivity between backend hosts"
for IP in ${BACKENDIP}; do
  $SSH -q -o BatchMode=yes -o ConnectTimeout=5 "$IP" exit
  if [ $? -ne 0 ]; then
    BAD "[SSH PASSWORDLESS CONNECTIVITY CHECK] SSH connectivity test FAILED on Host $IP"
    let SSHERRORS=$SSHERRORS+1
  fi
done

if [ $SSHERRORS -gt 0 ]; then 
  BAD "Please fix SSH connection between hosts"
  exit 1
else
  GOOD "[SSH PASSWORDLESS CONNECTIVITY CHECK] SSH connectivity test completed"
fi

function _distribute() {

NFRONT=$(ssh root@"$1" weka local resources | grep FRONTEND | wc -l)
NDRIVES=$(ssh root@"$1" weka local resources | grep DRIVES | wc -l)
NCOMPUTE=$(ssh root@"$1" weka local resources | grep COMPUTE | wc -l)
TCORES=$(( $NFRONT + $NDRIVES + $NCOMPUTE ))

NOTICE "VALIDATING CURRENT CORE VALUES"
if [[ "$NFRONT" = "$FRONT" || $NDRIVES = "$DRIVE" || "$TCORES" = "$TOTALC" ]]; then
  GOOD "Skipping host core changes not needed."
  return
fi

NOTICE "DOWNLOADING NECESSARY FILES"
curl -Lo $FILE https://weka-field-scripts.s3.amazonaws.com/update_core_config.py >/dev/null

if [ ! -e "$FILE" ]; then
  BAD "Unable to download file"
  exit
else
  GOOD "File downloaded successfully"
fi

NOTICE "VERIFYING $FILE PERMISSIONS"
FPERM=$(stat -c "%a %n" $FILE | cut -c1-3)
if [ "$FPERM" != 775 ]; then
  NOTICE "MAKING $FILE EXECUTABLE"
  chmod 775 $FILE
else
  GOOD "File Permission are set correctly"
fi

NOTICE "DISTRIBUTING FILE TO HOST $1"
  scp -p "$FILE" root@"$1":/$DIR > /dev/null
  if [ $? -ne 0 ]; then
    BAD "Unable to SCP @FILE to $1"
    WARN "Skipping $1"
    return
  else
    GOOD "$FILE transferred successfully"
  fi

NOTICE "EXECUTING CORE CHANGES TO HOST $1"

  ssh root@"$1" "$DIR/update_core_config.py $TOTALC $DRIVE $FRONT"

  _sleep "$BSLEEP"

NOTICE "VERIFYING REBUILD STATUS COMPLETE"
WARN "Waiting for rebuild to complete please standby..."
  while : ; do
    REBUILDSTATUS="$(weka status rebuild -J | awk '/progressPercent/ {print $2}' | tr -d ',')"
    echo -ne "$REBUILDSTATUS%\\r"
    if [ "$REBUILDSTATUS" = 0 ]; then
      GOOD "Rebuild complete.   "
      break
    fi
  done

NOTICE "VERIFYING NODE STATUS"
WARN "Waiting for nodes belonging to $1 to rejoin cluster"
  while : ; do
    WEKABKNODESSTATUS=$(weka cluster nodes -b --no-header -o id,role,hostname,ips,status | grep "$1" | grep -v UP | awk '{print $1}')
    if [ -z "$WEKABKNODESSTATUS" ]; then
      GOOD "All Nodes belonging to $1 in UP status."
      break
    fi
  done

NOTICE "VALIDATING SETTING"
if [[ "$NFRONT" != "$FRONT" || $NDRIVES != "$DRIVE" || "$TCORES" != "$TOTALC" ]]; then
  BAD "Failed applying new core allocations to HOST $1"
  weka debug manhole -s 0 set_grim_reaper_grace secs=30 > /dev/null
  weka debug jrpc config_override_key key=clusterInfo.allowChangingActiveHostNodes value=false > /dev/null
  exit 1
else
  GOOD "New core changes applied successfully"
fi
}

BKHOSTNAME=$(weka cluster host -b --no-header -o hostname,status | awk '/UP/ {print $1}')

function client_blacklisting() {
  weka debug blacklist add --node "$1" --force
  if [[ -z $(weka debug blacklist --no-header list "$1") ]]; then
    BAD "Unable to add node $1 from blacklist"
  else
    GOOD "Node ID $1 belonging host $2 black listed successfully"
  fi
}

function client_remove_blacklisting() {
  weka debug blacklist remove --node "$1"
  if [[ -z $(weka debug blacklist --no-header list -o id | grep -w  "$1") ]]; then
     GOOD "Node ID $1 belonging to host $2 removed from blacklist successfully"
  else
    BAD "Unable to remove node $1 from blacklist"
  fi
}

function client_node_status() {
  runtime="5 minute"
  endtime=$(date -ud "$runtime" +%s)
  while [[ $(date -u +%s) -le $endtime ]]; do
      WEKACLNODESSTATUS=$(weka cluster nodes --no-header "$1" -o status)
    if [  "$WEKACLNODESSTATUS" == UP ]; then
      GOOD "Nodes $1 belonging to $2 in UP status."
      break
    fi
  done
}

function readlines () {
    local N="$1"
    local line
    local rc="1"

    for i in $(seq 1 $N); do
        read line
        if [ $? -eq 0 ]; then
            echo $line
            rc="0"
        else
            break
        fi
    done

    return $rc
}

function backend_blacklisting () {

if [[ "$BKLIST" != 0 ]]; then
  WARN "\nBLACKLISTING NODES BELONGING TO HOST $1"
  CURRHOST=$(weka local resources | awk '/Management/ {print $3}')
  WEKABKNODESID=$(weka cluster nodes -b --no-header -o id,role,hostname,ips,status | grep "$1")
  if [[ ! -z $( echo "$WEKABKNODESID" | grep "$CURRHOST") ]]; then
    WEKABKNODESID=$(weka cluster nodes -b --no-header -o id,role,hostname,ips,status | grep "$1" | grep -v MANAGEMENT | awk '{print $1}')
  else
    WEKABKNODESID=$(weka cluster nodes -b --no-header -o id,role,hostname,ips,status | grep "$1" | awk '{print $1}')
  fi

  NOTICE "VERIFYING NODES SUCCESSFULLY BLACKLISTED"
  for ID in ${WEKABKNODESID}; do
    weka debug blacklist add --node "$ID" --force
    if [[ -z $(weka debug blacklist --no-header list "$ID") ]]; then
      BAD "Unable to add node $ID belonging to $1 to blacklist"
    else
      GOOD "Node ID $ID belonging $1 blacked listed successfully"
    fi
  done

  _sleep 5

  NOTICE "VERIFYING NODE STATUS FOR $1"
  for ID in ${WEKABKNODESID}; do
    if [[ $(weka cluster nodes "$ID" --no-header -o status) == DOWN ]]; then
      GOOD "Node ID $ID status Down"
    else
      BAD "Node ID $ID status is Not Down"
    fi
  done

  _sleep 30

  NOTICE "REMOVING NODES FROM BLACKLIST FOR $1"
  for ID in ${WEKABKNODESID}; do
    weka debug blacklist remove --node "$ID"
    if [[ -z $(weka debug blacklist --no-header list -o id | grep -w $ID) ]]; then
      GOOD "Node ID $ID belonging $1 Removed from blacklist successfully"
    else
      BAD "Unable to remove node $ID belonging to $1 to blacklist"
    fi
  done

  _sleep 5

  NOTICE "VERIFYING REBUILD STATUS COMPLETE"
  WARN "Waiting for rebuild to complete please standby..."
  while : ; do
    REBUILDSTATUS="$(weka status rebuild -J | awk '/progressPercent/ {print $2}' | tr -d ',')"
    echo -ne "$REBUILDSTATUS%\\r"
    if [ "$REBUILDSTATUS" = 0 ]; then
      GOOD "Rebuild complete.   "
      break
    fi
  done

  NOTICE "VERIFYING NODE STATUS"
  WARN "Waiting for nodes belonging to $1 to rejoin cluster"
  while : ; do
      WEKABKNODESSTATUS=$(weka cluster nodes -b --no-header -o id,role,hostname,ips,status | grep "$1" | grep -v UP | awk '{print $1}')
    if [ -z "$WEKABKNODESSTATUS" ]; then
      GOOD "All Nodes belonging to $1 in UP status."
      break
    fi
  done

  _sleep "$BSLEEP"

fi
}


main() {

NOTICE "DISABLING GRIM REAPER"
# need to disable grimreaper
weka debug manhole -s 0 disable_grim_reaper > /dev/null

sleep 5

if [ $(weka local run /weka/cfgdump | grep grimReaperEnabled | cut -d":" -f2 | tr -d " "',') == false ]; then
  GOOD "Grim reaper disabled successfully"
else
  BAD "Unable to modify grim reaper settings"
  exit 1
fi

NOTICE "MODIFYING SYSTEM SETTINGS TO ALLOW CORE ALLOCATION CHANGE"
# need to enable config to change core allocation
weka debug jrpc config_override_key key=clusterInfo.allowChangingActiveHostNodes value=true > /dev/null

sleep 5

if [ $(weka local run /weka/cfgdump | grep allowChangingActiveHostNodes | cut -d":" -f2 | tr -d " "',') == true ]; then
  GOOD "Core allocation settings applied successfully"
else
  BAD "Unable to make configuration change"
  exit 1
fi

if [ -z "$BACKEND" ]; then
  for HOST in ${BACKENDIP}; do
    _distribute "$HOST"
  done
else
  _distribute "$BACKEND"
fi

if [[ ! -z "$BACKEND" ]]; then
NOTICE "VALIDATING BACKEND HOST"
  HTYPE=$(weka cluster host -o ips,mode | grep -w "$BACKEND" | grep backend)
  HNAME=$(weka cluster host -o hostname,ips | grep -w "$BACKEND" | awk '{print $1}')
  if [ -z "${HTYPE}" ]; then
    BAD "Please provide valid IP of a backend host"
    exit
  else
    GOOD "Backend host verified"
    NOTICE "BACKEND BLACKLISTING"
    backend_blacklisting "$HNAME"
  fi
fi

NOTICE "BACKEND BLACKLISTING"
if [[ -z "$BACKEND" ]]; then
  for HOST in ${BKHOSTNAME}; do
    backend_blacklisting $HOST
  done
fi

if [[ "$BKLIST" -eq 0 ]]; then
  WARN "\nSKIPPING BACKEND BLACKLISTING"
fi

NOTICE "WORKING ON CLIENT HOSTS"
if [ -s "$CLIENTHOST" ]; then
  if [ "$NC" -ne 0 ]; then
    while dataset=$(readlines $NC); do

      for i in "$dataset"; do
        nodes+=( $(weka cluster nodes --no-header -o id,role,hostname,ips,status | grep "$i" | awk '{print $1}') )
      done

      NOTICE "BLACKLISTING NODES BELONGING TO CLIENT HOST"
      for i in "${nodes[@]}"; do
        HNAME=$(weka cluster nodes --no-header "$i" -o hostname)
        client_blacklisting "$i" "$HNAME"
      done

      _sleep 15

      echo -e "\n"

      NOTICE "REMOVING NODES FROM BLACKLIST FOR CLIENT HOST"
      for i in "${nodes[@]}"; do
        HNAME=$(weka cluster nodes --no-header "$i" -o hostname)
        client_remove_blacklisting "$i" "$HNAME"
      done

      NOTICE "VERIFYING NODE STATUS"
      for i in "${nodes[@]}"; do
        HNAME=$(weka cluster nodes --no-header "$i" -o hostname)
        client_node_status "$i" "$HNAME"
      done

      unset nodes

      _sleep "$CSLEEP"

      echo -e "\n"

    done < $CLIENTHOST
  else
    WARN "Skipping client host blacklisting"
  fi
else
  WARN "No online clients found"
fi

NOTICE "ENABLING GRIM reaper"
# need to enable grimreaper
weka debug manhole -s 0 enable_grim_reaper > /dev/null
weka debug manhole -s 0 set_grim_reaper_grace secs=30 > /dev/null

sleep 5

if [ $(weka local run /weka/cfgdump | grep grimReaperEnabled | cut -d":" -f2 | tr -d " "',') == true ]; then
  GOOD "Grim reaper enabled successfully"
else
  BAD "Unable to modify grim reaper settings"
  WARN "Manually issue command weka debug manhole -s 0 set_grim_reaper_grace secs=30"
fi

NOTICE "DISABLING CORE ALLOCATION CHANGE"
# need to disable config to change core allocation
weka debug jrpc config_override_key key=clusterInfo.allowChangingActiveHostNodes value=false > /dev/null

sleep 5

if [ $(weka local run /weka/cfgdump | grep allowChangingActiveHostNodes | cut -d":" -f2 | tr -d " "',') == false ]; then
  GOOD "Core allocation settings applied successfully"
else
  BAD "Unable to make configuration change"
  WARN "Manually issue command weka debug jrpc config_override_key key=clusterInfo.allowChangingActiveHostNodes value=false"
fi
}

main "$@"
