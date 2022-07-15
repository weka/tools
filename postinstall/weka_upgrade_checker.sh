#!/usr/bin/env bash

#version=1.0.39

# Colors
export NOCOLOR="\033[0m"
export CYAN="\033[0;36m"
export YELLOW="\033[1;33m"
export RED="\033[0;31m"
export GREEN="\033[1;32m"
export BLUE="\033[1;34m"

DIR='/tmp'
SSHCONF="$DIR/ssh_config"
LOG="$DIR/weka_upgrade_checker_`date +"%Y%m%dT%I%M%S"`.log"
LARGE_CLUSTER=100 #Total number of hosts and clients in cluster
HOSTSPACE1=6000 #Minimum Free space on BACKEND in /weka specified in MBs
HOSTSPACE2=50 #Minimum Free space on BACKEND in /opt/weka/logs specified in MBs
HOSTSPACEMIN=25 #Absolute Minimum Free space on BACKEND in /opt/weka/logs specified in MBs "ONLY on small clusters"
CLIENTSPACE1=5000 #Minimum Free space on CLIENTS in /weka specified in MBs
CLIENTSPACE2=10 #Minimum Free space on CLIENTS in /opt/weka/logs specified in MBs
CLIENTSPACEMIN=5 #Absolute Minimum Free space on CLIENTS in /opt/weka/logs specified in MBs "ONLY on small clusters"

usage()
{
cat <<EOF
Usage: [-a for AWS instance.]
Usage: [-c for skipping client upgrade checks.]
Usage: [-r Check remote system. Enter valid ip address of a weka backend or client.]
Usage: [-x Only report exceptions/errors on hosts.]
This script checks Weka Clusters for Upgrade eligibility. On non-AWS instances you must run the script as root user.
OPTIONS:
  -a  Creates a specific aws ssh config file for AWS instance.
  -s  Skips client checks
  -r  Check specific remote system. Enter valid ip address of a weka backend or client.
  -o  Include additional checks for rolling upgrade.
  -x  Only report exceptions/errors.
EOF
exit
}

while getopts ":asoxhr:" opt; do
        case ${opt} in
          a ) AWS=1
          ;;
          s ) SKPCL=true
          ;;
          r ) RHOST=${OPTARG}
          shift
          ;;
          o ) ROLL=1
          shift
          ;;
          x ) XCEPT=true
          shift
          ;;
          h ) usage
          ;;
          * ) echo "Invalid Option Try Again!"
       usage
          ;;
        esac
done

shift $((OPTIND -1))

if [ ! -z $AWS ]; then
cat > $SSHCONF <<EOF
BatchMode yes
Compression yes
CompressionLevel 9
StrictHostKeyChecking no
PasswordAuthentication no
ConnectTimeout 5
GlobalKnownHostsFile $DIR/global_known_hosts
IdentityFile /home/ec2-user/.ssh/support_id_rsa.pem
EOF
fi

if [ -z $AWS ]; then
  SSH='/usr/bin/ssh'
else
  SSH="/usr/bin/ssh -F /tmp/ssh_config -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
fi

function logit() {
  echo -e "[${USER}][$(date)] - ${*}\n" >> ${LOG}
}

function LogRotate () {
local f="$1"
local limit="$2"
# Deletes old log file
  if [ -f "$f" ] ; then
    CNT=${limit}
    let P_CNT=CNT-1
  if [ -f "${f}"."${limit}" ] ; then
    rm "${f}"."${limit}"
  fi

# Renames logs .1 trough .3
while [[ $CNT -ne 1 ]] ; do
  if [ -f "${f}"."${P_CNT}" ] ; then
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

LogRotate $LOG 3

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

if [ ! -z "$RHOST" ]; then
  if ! [[ $RHOST =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
  BAD "Must enter a valid ip address, cannot continue."
    exit 1
  fi
fi

if [ -z "$AWS" ]; then
  if [ "$(id -u)" -ne 0 ]; then
    BAD "Must run as root user, cannot continue."
    exit 1
  fi
fi

NOTICE "VERIFYING WEKA AGENT"
WEKAVERIFY=$(lsmod | grep -i weka)
if [ -z "$WEKAVERIFY" ]; then
  BAD "Weka is NOT installed on host or the container is down, cannot continue."
  exit 1
else
WEKAVERSION=$(weka version current)
MAJOR=$(weka version current | cut -d "." -f1)
WEKAMINOR1=$(weka version current | cut -d "." -f2)
WEKAMINOR2=$(weka version current | cut -d "." -f3)
  GOOD "Weka verified $WEKAVERSION."
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
CONSTATUS=$(weka local ps --no-header -o name,running | grep -i TRUE)
if [ -z "$CONSTATUS" ]; then
  BAD "Weka local container is down cannot continue."
  exit
else
  GOOD "Weka local container is running."
fi

if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 13 ]]; then
  if [ $(weka status -J | awk '/"link_layer"/ {print $2}' | tr -d '"') != ETH ]; then
    WARN "Upgrading to 3.14 not supported. Requires Weka to use Ethernet connectivity. Please reach out to customer success on an ETA for IB support."
  else
    WARN "Upgrading to 3.14 requires Minimum OFED 4.6"
  fi
fi

if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 14 ]]; then
  if [ $(weka status -J | awk '/"link_layer"/ {print $2}' | tr -d '"') = ETH ]; then
    WARN "Upgrading to 4.0 not supported. Requires Weka to use Ethernet connectivity and minimum Weka version 3.14.1 or greater"
  fi
fi

if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 14 ]] && [[ "$WEKAMINOR2" -ge 1 ]]; then
  if [ $(weka status -J | awk '/"link_layer"/ {print $2}' | tr -d '"') != ETH ]; then
    WARN "Upgrading to 4.0 not supported. Requires Weka to use Ethernet connectivity. Please reach out to customer success on an ETA for IB support."
  else
    WARN "Upgrading to 4.0 requires Minimum OFED 5.1"
  fi
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
REBUILDSTATUS="$(weka status rebuild -J | awk '/progressPercent/ {print $2}' | tr -d ',')"
if [ "$REBUILDSTATUS" != 0 ]; then
  BAD "Rebuilding, CURRENT PROGRESS:$REBUILDSTATUS%"
else
  GOOD "No rebuild in progress."
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

NOTICE "VERIFYING WEKA FS SNAPSHOTS UPLOAD STATUS"
if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -ge 12 ]]; then
  WEKASNAP=$(weka fs snapshot --no-header -o id,name,remote_object_status,remote_object_progress | grep -i upload)
else
  WEKASNAP=$(weka fs snapshot --no-header -o name,stow,object | grep -i upload)
fi

if [ -z "$WEKASNAP" ]; then
  GOOD "Weka snapshot upload status ok."
else
  BAD "Following snapshots are being uploaded."
  WARN "\n$WEKASNAP\n"
fi

NOTICE "VERIFYING IF SMALL WEKA FILE SYSTEMS EXISTS"
SMALLFS=$(weka fs -o name,availableSSD -R --no-header | awk '$2< 1073741824')
if [ -z "$SMALLFS" ]; then
  GOOD "No small Weka file system found."
else
  BAD "Following small file systems identified, minimum size must be increased to 1GB."
  WARN "\n$SMALLFS\n"
fi

if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 12 ]]; then
  NOTICE "VERIFYING RAID REDUCTION SETTINGS"
  sudo weka local run /weka/cfgdump > $DIR/cfgdump.txt
  if [ $? -eq 0 ]; then
    RAID=$(awk '/clusterInfo/{f=1} f && /reserved/ {getline ; getline ; print ($0+0); exit}' $DIR/cfgdump.txt)
      if [ $RAID -eq 1 ]; then
        GOOD "Raid Reduction is disabled."
      else
        BAD "Raid Reduction is ENABLED issue command 'weka debug jrpc config_override_key key='clusterInfo.reserved[1]' value=1' to disable."
      fi
  else
    WARN "Unable to verify Raid Reduction settings."
  fi
fi

#squelch check on version 3.9 WEKAPP-229504
if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 9 ]]; then
  NOTICE "VERIFYING BUCKET L2BLOCK ENTRIES"
  COMPUTENODEID=$(weka cluster nodes --no-header -o id,role | awk '/COMPUTE/ {print $1}')
  for ID in ${COMPUTENODEID}; do
    echo -ne "${CYAN}working on Compute NodeID $ID $NOCOLOR\033[Complete\r"
    L2BLOCK=$(weka debug manhole --node $ID buckets_get_registry_stats | awk  '/entriesInL2Block/{getline ; getline ; getline; gsub(",",""); print $2}' | awk '$1>= 477')
    if [ ! -z "$L2BLOCK" ]; then
      BAD -e "\nFound high L2BLOCK values for Weka buckets, Please contact Weka Support prior to upgrade Ref:WEKAPP-229504."
      WARN "$(weka cluster nodes $ID -o id,hostname,role)"
    fi
  done
  GOOD "\nBucket L2BLOCK check completed"
fi

NOTICE "VERIFYING SSD FIRMWARE"
SSD=$(weka cluster drive --no-header -o uuid,hostname,vendor,firmware,model | grep -i EDB5002Q)
if [ -z "$SSD" ]; then
  GOOD "SSD Firmware check completed."
else
  BAD "The following SSDs might be problematic contact support."
  WARN "\n$SSD\n"
fi

NOTICE "VERIFYING WEKA CLUSTER DRIVE STATUS"
WEKADRIVE=$(weka cluster drive --no-header -o id,uuid,hostname,status | grep -v ACTIVE)
if [ -z "$WEKADRIVE" ]; then
  GOOD "All drives are in OK status."
else
  BAD "The following Drives are not Active."
  WARN "\n$WEKADRIVE\n"
fi

NOTICE "VERIFYING WEKA TRACES STATUS"
if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -ge 10 ]]; then
  WEKATRACE=$(weka debug traces status | awk 'NR==1 {print $3}')
else
  WEKATRACE=$(weka local exec /usr/local/bin/supervisorctl status weka-trace-dumper | tr -d '\n' | awk '{print $2}')
fi

if [[ "$WEKATRACE" == "enabled." || "$WEKATRACE" == "RUNNING" ]]; then
  GOOD "Weka traces are enabled."
else
  BAD "Weka traces are not enabled."
  WARN "Please enable Weka traces using 'weka debug traces start'"
fi

#client version during production can run n-1 however during upgrade they need to be on the same version as cluster otherwise after upgrade they will be n-2.
NOTICE "VERIFYING CLIENT WEKA VERSION"
CLIENTFVER=$(weka cluster host --no-header -c -o hostname,ips,software | grep -v "$MAJOR.$WEKAMINOR1")
if [ -z "$CLIENTFVER" ]; then
  GOOD "All Weka clients on correct version."
else
  CLIENTFVER=$(weka cluster host -c -o hostname,ips,software | grep -v "$MAJOR.$WEKAMINOR1")
  BAD "The following Weka clients should be upgraded to $WEKAVERSION."
  WARN "\n$CLIENTFVER\n"
fi

NOTICE "CHECKING FOR MANUAL WEKA OVERRIDES"
OVERRIDE=$(weka debug override list --no-header)
if [ -z "$OVERRIDE" ]; then
  GOOD "No manual Weka overrides found."
else
  OVERRIDE=$(weka debug override list)
  WARN "Manual Weka overrides found"
  WARN "\n$OVERRIDE\n"
fi

function check_ssh_connectivity() {
  if $SSH -o ConnectTimeout=5 "$1" exit &>/dev/null; then
    if [[ ! $XCEPT ]] ; then GOOD " [SSH PASSWORDLESS CONNECTIVITY CHECK] SSH connectivity test PASSED on Host $2 $1"
    fi
  else
    BAD " [SSH PASSWORDLESS CONNECTIVITY CHECK] SSH connectivity test FAILED on Host $2 $1"
    return 1
  fi
}

function check_jq() {
  if ! $SSH $1 command -v jq &>/dev/null; then
    BAD " [JQ CHECK ROLLING UPGRADE] 'jq' executable was not found on host $2"
  else
    GOOD " [JQ CHECK ROLLING UPGRADE] 'jq is installed on host $2'"
  fi
}

function weka_user_login() {
if [ "$1" == "error: Authentication Failed: " ]; then
  BAD " [WEKA USER LOGIN TEST ROLLING UPGRADE] Please login using weka user login on host $2"
else
  GOOD " [WEKA USER LOGIN TEST ROLLING UPGRADE] Weka user login successful on host $2."
fi
}

function weka_agent_service() {
  if [ "$1" == "active" ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [WEKA AGENT SERVICE] Weka Agent Serivce is running on host $2"
    fi
  else
    BAD " [WEKA AGENT SERVICE] Weka Agent Serivce is NOT running on host $2"
  fi
}

function diffdate() {
  local DIFF
  if [ -z "$1" ]; then
    BAD " [TIME SYNC CHECK] Unable to determine time on Host $2."
    return 1
  fi

  DIFF=$(( $(date --utc '+%s') - $1 ))
  if [ "$DIFF" -lt 0 ]; then
    let DIFF="(( 0 - "$DIFF" ))"
  fi

  if [ "$DIFF" -gt 60 ]; then
    BAD " [TIME SYNC CHECK] There is a time difference of greater than 60s between Host $(hostname) and $2, time difference of ${DIFF}s."
  else
    if [[ ! $XCEPT ]] ; then GOOD " [TIME SYNC CHECK] Time in sync between host $(hostname) and $2 total difference ${DIFF}s."
    fi
  fi
}

function weka_container_status() {
  if [ -z "$1" ]; then
    BAD " [WEKA CONTAINER STATUS] Unable to determine container status on Host $2."
    return 1
  fi

  if [ "$1" != "True" ]; then
    BAD " [WEKA CONTAINER STATUS] Weka local container is down on Host $2."
  else
    if [[ ! $XCEPT ]] ; then GOOD " [WEKA CONTAINER STATUS] Weka local container is running Host $2."
    fi
  fi
}

function weka_container_disabled() {
  if [ -z "$1" ]; then
    BAD " [WEKA CONTAINER STATUS] Unable to determine container status on Host $2."
    return 1
  fi

  if [ "$1" = "True" ]; then
    BAD " [WEKA CONTAINER STATUS] Weka local container is disabled on Host $2, please enable using weka local enable."
  else
    if [[ ! $XCEPT ]] ; then GOOD " [WEKA CONTAINER STATUS] Weka local container is running Host $2."
    fi
  fi
}

LOGSDIR1='/opt/weka'
LOGSDIR2='/opt/weka/logs'
TOTALHOSTS=$(weka cluster host --no-header | wc -l)
function freespace_backend() {
  if [ -z "$1" ]; then
    BAD " [FREE SPACE CHECK] Unable to determine free space on Host $3."
    return 1
  fi

  if [ "$1" -lt "$HOSTSPACE1" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has less than recommended free space of ~$(($1 / 1000))GB in $LOGSDIR1."
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786"
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 has recommended free space of ~$(($1 / 1000))GB in $LOGSDIR1."
      fi
  fi

  if [[ "$TOTALHOSTS" -ge "$LARGE_CLUSTER" && "$2" -lt "$HOSTSPACE2" ]]; then
    BAD " [FREE SPACE CHECK] Host $3 has less than recommended free space of $2MB in $LOGSDIR2"
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786"
    return 1
  fi

  if [ "$2" -lt "$HOSTSPACEMIN" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $2MB in $LOGSDIR2."
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786"
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 has Recommended Free Space of $2MB in $LOGSDIR2."
    fi
  fi
}

# Check for any upgrade container, these should be removed before upgrading if found.
function upgrade_container() {
  if [ -z "$1" ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [UPGRADE CONTAINER CHECK] No upgrade containers found on Host $2."
    fi
  else
    BAD " [UPGRADE CONTAINER CHECK] Upgrade container found on Host $2 status $1."
  fi
}

# Check for any Weka filesystems mountd on /weka
function weka_mount() {
  if [ -z "$1" ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING WEKA MOUNT] NO Mount point on '/weka' found on Host $2."
    fi
  else
    BAD " [CHECKING WEKA MOUNT] Mount point on '/weka' found on Host $2."
  fi
}

# Check for any invalid IP addresses in Weka resources. See https://wekaio.atlassian.net/wiki/spaces/MGMT/pages/1503330580/Cleaning+up+backend+IPs+on+systems+upgraded+to+3.8
function weka_ip_cleanup() {
  if [ "$1" -eq 0 ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING IP WEKA RESOURCES] $1 invalid IP addresses found in Weka resources on Host $2."
    fi
  else
    BAD " [CHECKING IP WEKA RESOURCES] $1 Invalid IP addresses in weka resources found on Host $2. Need to run update_backend_ips.py on this backend"
    WARN "  [CHECKING IP WEKA RESOURCES] https://wekaio.atlassian.net/wiki/spaces/MGMT/pages/1503330580/Cleaning+up+backend+IPs+on+systems+upgraded+to+3.8"
  fi
}

# Check for any SMB containers, these may need stopping BEFORE upgrade.
function smb_check() {
  if [ -z "$1" ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING SMB RESOURCES] NO SMB containers found on Host $2."
    fi
  else
    WARN " [CHECKING SMB RESOURCES] Found SMB resources on Host $2. Recommend stopping SMB container before upgrade on this backend."
  if [ "$3" -gt 10000000 ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING AVAILABLE MEMORY] Sufficient memory found on $2."
    fi
  else
    WARN "  [CHECKING AVAILABLE MEMORY] Insufficient memory found on Host $2 running SMB, minimum required 10GB."
  fi
fi
}

function freespace_client() {
  if [ -z "$1" ]; then
    BAD " [FREE SPACE CHECK] Unable to Determine Free Space on Host $3."
    return 1
  fi

  if [ "$1" -lt "$CLIENTSPACE1" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $(($1 / 1000))GB in $LOGSDIR1."
    WARN " [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786"
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 has Recommended Free Space of $(($1 / 1000))GB in $LOGSDIR1."
    fi
  fi

  if [[ "$TOTALHOSTS" -ge "$LARGE_CLUSTER" && "$2" -lt "$CLIENTSPACE2" ]]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $2MB in $LOGSDIR2"
    WARN " [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786"
    return 1
  fi

  if [ "$2" -lt "$CLIENTSPACEMIN" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $2MB in $LOGSDIR2."
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786"
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 has Recommended Free Space of $2MB in $LOGSDIR2."
    fi
  fi
}

function client_web_test() {
  if [ "$1" = 200 ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [HTTP CONNECTIVITY TEST] HTTP connectivity is up."
    fi
  elif [  "$1" = 5 ]; then
    WARN "  [HTTP CONNECTIVITY TEST] Blocked by Web Proxy."
  else
    BAD " [HTTP CONNECTIVITY TEST] Internet access maybe down."
  fi
}

BACKEND=$(weka cluster host -b --no-header -o ips | awk -F, '{print $1}')
CLIENT=$(weka cluster host -c --no-header -o ips | awk -F, '{print $1}')

function backendloop() {
local CURHOST REMOTEDATE WEKACONSTATUS RESULTS1 RESULTS2 UPGRADECONT MOUNTWEKA SMBCHECK
  CURHOST=$(weka cluster host --no-header -o hostname,ips | grep -w "$1" | awk '{print $1}')
  NOTICE "VERIFYING SETTINGS ON BACKEND HOST $CURHOST"
  check_ssh_connectivity "$1" "$CURHOST" || return

  REMOTEDATE=$($SSH "$1" "date --utc '+%s'")
  diffdate "$REMOTEDATE" "$CURHOST"

  RESULTS1=$($SSH "$1" df -m "$LOGSDIR1" | awk '{print $4}' | tail -n +2)
  RESULTS2=$($SSH "$1" df -m "$LOGSDIR2" | awk '{print $4}' | tail -n +2)
  freespace_backend "$RESULTS1" "$RESULTS2" "$CURHOST"

  MOUNTWEKA=$($SSH "$1" "mountpoint -qd /weka/")
  weka_mount "$MOUNTWEKA" "$CURHOST"

  WEKAAGENTSRV=$($SSH "$1" sudo systemctl is-active weka-agent.service)
  weka_agent_service "$WEKAAGENTSRV" "$CURHOST"

  WEKACONSTATUS=$($SSH "$1" weka local ps --no-header -o name,running | grep -i default | awk '{print $2}')
  weka_container_status "$WEKACONSTATUS" "$CURHOST" || return

  CONDISABLED=$($SSH "$1" weka local ps --no-header -o name,disabled | grep -E 'client|default' | awk '{print $2}')
  weka_container_disabled "$CONDISABLED" "$CURHOST"

  SMBCHECK=$($SSH "$1" "weka local ps | grep samba")
  AMEMORY=$($SSH "$1" cat /proc/meminfo | awk '/MemAvailable:/ {print $2}')
  smb_check "$SMBCHECK" "$CURHOST" "$AMEMORY"

  UPGRADECONT=$($SSH "$1" "weka local ps --no-header -o name,running | awk '/upgrade/ {print $2}'")
  upgrade_container "$UPGRADECONT" "$CURHOST"

  if [ ! -z $AWS ]; then
    IPCLEANUP=$($SSH "$1" "sudo weka local resources -J | grep -c -E -o '([0]{1,3}[\.]){3}[0]{1,3}'")
     weka_ip_cleanup "$IPCLEANUP" "$CURHOST"
  else
    IPCLEANUP=$($SSH "$1" "weka local resources -J | grep -c -E -o '([0]{1,3}[\.]){3}[0]{1,3}'")
     weka_ip_cleanup "$IPCLEANUP" "$CURHOST"
  fi

  if [ ! -z $ROLL ]; then
  WEKALOGIN=$($SSH "$1" "weka cluster nodes 2>&1 | awk '/error:/'")
  weka_user_login "$WEKALOGIN" "$CURHOST"
  fi

  if [ ! -z $ROLL ]; then
  check_jq "$1" "$CURHOST"
  fi

  if [ $XCEPT ];then
    WARN "Backend host checks completed please see logs for details $LOG"
  fi
}

function clientloop() {
local CURHOST REMOTEDATE WEKACONSTATUS RESULTS1 RESULTS2 UPGRADECONT MOUNTWEKA
  CURHOST=$(weka cluster host --no-header -o hostname,ips | grep -w "$1" | awk '{print $1}')
  NOTICE "VERIFYING SETTINGS ON CLIENTs HOST $CURHOST"
  check_ssh_connectivity "$1" "$CURHOST" || return

  RESULTS1=$($SSH "$1" df -m "$LOGSDIR1" | awk '{print $4}' | tail -n +2)
  RESULTS2=$($SSH "$1" df -m "$LOGSDIR2" | awk '{print $4}' | tail -n +2)
  freespace_client "$RESULTS1" "$RESULTS2" "$CURHOST"

  WEBTEST=$($SSH "$1" curl -sL -w "%{http_code}" "http://www.google.com/" -o /dev/null)
  client_web_test "$WEBTEST"

  REMOTEDATE=$($SSH "$1" "date --utc '+%s'")
  diffdate "$REMOTEDATE" "$CURHOST"

  MOUNTWEKA=$($SSH "$1" "mountpoint -qd /weka/")
  weka_mount "$MOUNTWEKA" "$CURHOST"

  WEKAAGENTSRV=$($SSH "$1" sudo systemctl is-active weka-agent.service)
  weka_agent_service "$WEKAAGENTSRV" "$CURHOST"

  WEKACONSTATUS=$($SSH "$1" weka local ps --no-header -o name,running | grep -E 'client|default' | awk '{print $2}')
  weka_container_status "$WEKACONSTATUS" "$CURHOST"

  UPGRADECONT=$($SSH "$1" "weka local ps --no-header -o name,running | awk '/upgrade/ {print $2}'")
  upgrade_container "$UPGRADECONT" "$CURHOST"

  if [ $XCEPT ];then
    WARN "Client checks completed please see logs for details $LOG"
  fi
}

main() {
# this is for the -r flag usage.
KHOST=$(weka cluster host -o ips,mode | grep -w "$RHOST" | awk '{print $2}')
if [ -z "$KHOST" ]; then
  BAD "IP Address invalid, enter an ip address of a known Weka client or host."
  exit 1
elif [[ "$RHOST" && "$KHOST" == "backend" ]]; then
  for ip in ${KHOST}; do
    backendloop "$RHOST" || continue
  done
  exit
fi

if [ -z "$KHOST" ]; then
  BAD "IP Address invalid, enter an ip address of a known Weka client or host."
  exit 1
elif [[ "$RHOST" && "$KHOST" == "client" ]]; then
  for ip in ${KHOST}; do
    clientloop "$RHOST" || continue
  done
  exit
fi

for ip in ${BACKEND}; do
  backendloop "$ip" || continue
done

if [ "$SKPCL" == "true" ]; then
  NOTICE "SKIPPING CLIENTs UPGRADE CHECKs"
else
  for ip in ${CLIENT}; do
    clientloop "$ip" || continue
  done
fi
}

main "$@"
