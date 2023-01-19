#!/usr/bin/env bash

#version=1.0.61

# Colors
export NOCOLOR="\e[0m"
export CYAN="\e[36m"
export YELLOW="\e[1;33m"
export RED="\e[1;91m"
export GREEN="\e[32m"
export BLUE="\e[34m"
export MAGENTA="\e[1;35m"

DIR='/tmp'
SSHCONF="$DIR/ssh_config"
LOG="$DIR/weka_upgrade_checker.log"
LARGE_CLUSTER=100 #Total number of hosts and clients in cluster
HOSTSPACE1=6000 #Minimum Free space on BACKEND in /weka specified in MBs
HOSTSPACE2=50 #Minimum Free space on BACKEND in /opt/weka/logs specified in MBs
DATASPACE=10000 #Size of data dir should not be larger then 10GB irrespective of /opt/weka
HOSTSPACEMIN=25 #Absolute Minimum Free space on BACKEND in /opt/weka/logs specified in MBs "ONLY on small clusters"
CLIENTSPACE1=5000 #Minimum Free space on CLIENTS in /weka specified in MBs
CLIENTSPACE2=10 #Minimum Free space on CLIENTS in /opt/weka/logs specified in MBs
CLIENTSPACEMIN=5 #Absolute Minimum Free space on CLIENTS in /opt/weka/logs specified in MBs "ONLY on small clusters"

usage() {
cat <<EOF
Usage: [-a for AWS instance.]
Usage: [-s for skipping client upgrade checks.]
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

if [ ! -z "$AWS" ]; then
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

if [ -z "$AWS" ]; then
  SSH='/usr/bin/ssh'
else
  SSH="/usr/bin/ssh -F /tmp/ssh_config -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
fi

function logit() {
  echo -e "[${USER}][$(date)] - ${*}\n" >> "${LOG}"
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
    while [[ $CNT -ne 1 ]]; do
      if [ -f "${f}"."${P_CNT}" ]; then
        mv "${f}"."${P_CNT}" "${f}"."${CNT}"
        LOG="${f}"."${P_CNT}"
      fi
      let CNT=CNT-1
      let P_CNT=P_CNT-1
    done

# Renames current log to .1
      echo "" > "$f"
      mv "$f" "${f}".1
  fi
}

LogRotate "$LOG" 3

function NOTICE() {
echo -e "\n${MAGENTA}$1${NOCOLOR}"
logit "${MAGENTA}""[$1]""${NOCOLOR}"
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

NOTICE "VERIFYING WEKA AGENT STATUS"
WEKAVERIFY=$(lsmod | grep -i weka)
if [ -z "$WEKAVERIFY" ]; then
  BAD "Weka is NOT installed on host or the container is down, cannot continue."
  exit 1
else
WEKAVERSION=$(weka version current)
MAJOR=$(weka version current | cut -d "." -f1)
WEKAMINOR1=$(weka version current | cut -d "." -f2)
WEKAMINOR2=$(weka version current | cut -d "." -f3)
  GOOD "Weka agent status verified."
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
CONSTATUS=$(weka local ps --no-header -o name,running | awk '/default/{print $2}')
if [ -z "$CONSTATUS" ]; then
  BAD "Weka local container is down cannot continue."
  exit
else
  GOOD "Weka local container is running."
fi

if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 13 ]]; then
  NOTICE "VERIFYING UPGRADE ELIGIBILITY"
  if [ "$(weka status -J | awk '/"link_layer"/ {print $2}' | tr -d '"')" != ETH ]; then
    WARN "Upgrading to 3.14 not supported. Requires Weka to use Ethernet connectivity. Please reach out to customer success on an ETA for IB support."
  else
    WARN "Upgrading to 3.14 requires Minimum OFED 5.1-2.5.8.0."
  fi
fi

if [[ "$MAJOR" -eq 3 && "$WEKAMINOR1" -eq 14 ]] || [[ "$MAJOR" -eq 3 && "$WEKAMINOR1" -eq 14 && "$WEKAMINOR2" -ge 1 ]]; then
  NOTICE "VERIFYING UPGRADE ELIGIBILITY"
  if [ "$(weka status -J | awk '/"link_layer"/ {print $2}' | tr -d '"')" != ETH ]; then
    WARN "Upgrading to 4.0 not supported. Requires Weka to use Ethernet connectivity and minimum Weka version 3.14.1 or greater."
  else
    GOOD "Cluster is upgrade eligible"
  fi
fi

if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 14 ]]; then
  NOTICE "VERIFYING PROBLEMATIC DRIVES"
  DRIVES=$(weka cluster drive -o vendor --no-header | grep -i KIOXIA)
  if [ ! -z "$DRIVES" ]; then
    WARN "Contact Weka Support prior to upgrading to Weka 4.0, System identified with Kioxia drives."
  else
    GOOD "No problematic drives found"
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
  BAD "Rebuilding, CURRENT PROGRESS:$REBUILDSTATUS%."
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
  WEKANODES=$(weka cluster nodes -o id,hostname,status,role | grep -v UP)
  BAD "Failed Weka Nodes Found."
  WARN "\n$WEKANODES\n"
fi

NOTICE "VERIFYING WEKA FS SNAPSHOTS UPLOAD STATUS"
if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -ge 12 ]]; then
  WEKASNAP=$(weka fs snapshot --no-header -o id,name,remote_object_status,remote_object_progress | grep -i upload)
else
  WEKASNAP=$(weka fs snapshot --no-header -o name,remote_object_status,remote_object_progress | grep -i upload)
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
      if [ "$RAID" -eq 1 ]; then
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
    L2BLOCK=$(weka debug manhole --node "$ID" buckets_get_registry_stats | awk  '/entriesInL2Block/{getline ; getline ; getline; gsub(",",""); print $2}' | awk '$1>= 477')
    if [ ! -z "$L2BLOCK" ]; then
      BAD -e "\nFound high L2BLOCK values for Weka buckets, Please contact Weka Support prior to upgrade Ref:WEKAPP-229504."
      WARN "$(weka cluster nodes "$ID" -o id,hostname,role)"
    fi
  done
  GOOD "\nBucket L2BLOCK check completed."
fi

#Aggressive Dieting should be disabled prior to upgrading to 4.0.2
if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 14 ]]; then
  NOTICE "VERIFYING SYSTEM OPTIMAL SETTINGS"
    WARN "After upgrading to Weka 4.0.2, issue the following override command. 'weka debug config override clusterInfo.allowDietAggressively false'"
fi

#Aggressive Dieting should be disabled prior to upgrading to 4.0.2
if [ "$MAJOR" -eq 4 ]; then
  NOTICE "VERIFYING SYSTEM OPTIMAL SETTINGS"
  AGGRESSIVEDIET=$(sudo weka local run -C default /weka/cfgdump | grep allowDietAggressively | awk '{print $2}' | tr -d ",")
    if [ "$AGGRESSIVEDIET" == false ]; then
      GOOD "System checks passed"
    else
      BAD "Please contact Weka support Reference Agreessive Diet."
    fi
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
if [[ "$MAJOR" -ge 3 && "$WEKAMINOR1" -ge 10 ]] || [[ "$MAJOR" -ge 3 ]]; then
  WEKATRACE=$(weka debug traces status | awk 'NR==1 {print $3}')
else
  WEKATRACE=$(sudo weka local exec /usr/local/bin/supervisorctl status weka-trace-dumper | tr -d '\n' | awk '{print $2}')
fi

if [[ "$WEKATRACE" == "enabled." || "$WEKATRACE" == "RUNNING" ]]; then
  GOOD "Weka traces are enabled."
else
  BAD "Weka traces are not enabled."
  WARN "Please enable Weka traces using 'weka debug traces start'."
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
  WARN "Manual Weka overrides found."
  WARN "\n$OVERRIDE"
fi

if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 14 ]] || [[ "$MAJOR" -ge 4 ]]; then
NOTICE "CHECKING WEKA STATS RETENTION"
STATSRETENTION=$(weka stats retention status -J | awk '/"retention_secs":/ {print $2}' | tr -d ",")
  if [ "$STATSRETENTION" -le 172800 ]; then
    GOOD "Weka stats retention settings are set correctly."
  else
    BAD "Set stats retention to 2 days, execute 'weka stats retention set --days 2'. Following the upgrade revert back using 'weka stats retention set --days $(($STATSRETENTION / 86400))'."
  fi
fi


if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 12 ]]; then
  if [ $(weka cluster host --no-header | wc -l) -ge "$LARGE_CLUSTER" ]; then
     NOTICE "VERIFYING TLS SETTINGS"
     if [ $(sudo weka local run /weka/cfgdump | grep serializedTLSData -n20 | grep state | awk '{gsub("\"",""); print $3 }') == NONE ]; then
      GOOD "TLS is Disabled"
    else
      WARN "TLS is Enabled and should be disabled please contact Weka Support."
    fi
  fi
fi

function check_ssh_connectivity() {
  if $SSH -o ConnectTimeout=5 "$1" exit &>/dev/null; then
    if [[ ! $XCEPT ]] ; then GOOD " [SSH PASSWORDLESS CONNECTIVITY CHECK] SSH connectivity test PASSED on Host $2 $1."
    fi
  else
    BAD " [SSH PASSWORDLESS CONNECTIVITY CHECK] SSH connectivity test FAILED on Host $2 $1."
    return 1
  fi
}

function os_check() {

ID="$1"
VERSION_ID="$2"
VERSION="$3"
NAME="$4"

if [ "$ID" = 'centos' ]; then
  VERSION_ID=$(cat /etc/redhat-release)
  VERSION_ID=${VERSION_ID##*release }
  VERSION_ID=${VERSION_ID%.*}
elif [ "$ID" = 'ubuntu' ]; then
  VERSION_ID=${VERSION%% *}
fi

distro_not_found=0
version_not_found=0
unsupported_distro=0
unsupported_version=0
client_only=0

case $ID in
  'centos')
    case $VERSION_ID in
      '7.'[2-9]) ;;
      '8.'[0-5]) ;;
      '') version_not_found=1 ;;
      *) unsupported_version=1 ;;
    esac
    ;;

  'rhel')
    case $VERSION_ID in
      '7.'[2-9]) ;;
      '8.'[0-6]) ;;
      '') version_not_found=1 ;;
      *) unsupported_version=1 ;;
    esac
    ;;

  'rocky')
    case $VERSION_ID in
      '8.6') ;;
      '') version_not_found=1 ;;
      *) unsupported_version=1 ;;
    esac
    ;;

  'sles')
    case $VERSION_ID in
      '12.5') client_only=1 ;;
      '15.2') client_only=1 ;;
      '') version_not_found=1 ;;
      *) unsupported_version=1 ;;
    esac
    ;;

  'ubuntu')
    case $VERSION_ID in
      '18.04.'[0-6]) ;;
      '20.04.'[0-4]) ;;
      '') version_not_found=1 ;;
      *) unsupported_version=1 ;;
    esac
    ;;

  '') distro_not_found=1 ;;
  *) unsupported_distro=1 ;;
esac

if [ "$distro_not_found" -eq 1 ]; then
  BAD " [VERIFYING OS SUPPORT] Distribution not found."
elif [ "$version_not_found" -eq 1 ]; then
  BAD " [VERIFYING OS SUPPORT] $NAME detected but version not found."
elif [ "$unsupported_distro" -eq 1 ]; then
  BAD " [VERIFYING OS SUPPORT] $NAME is not a supported distribution."
elif [ "$unsupported_version" -eq 1 ]; then
  BAD " [VERIFYING OS SUPPORT] $NAME $VERSION_ID is not a supported version of $NAME."
else
  if [ "$client_only" -eq 1 ]; then
    GOOD " [VERIFYING OS SUPPORT] $NAME $VERSION_ID is supported (for client only)."
  else
    GOOD " [VERIFYING OS SUPPORT] $NAME $VERSION_ID is supported."
  fi
fi

}

function check_jq() {
  if ! $SSH "$1" command -v jq &>/dev/null; then
    BAD " [JQ CHECK ROLLING UPGRADE] 'jq' executable was not found on host $2."
  else
    GOOD " [JQ CHECK ROLLING UPGRADE] 'jq is installed on host $2'."
  fi
}

function weka_user_login() {
if [ "$1" == "error: Authentication Failed: " ]; then
  BAD " [WEKA USER LOGIN TEST ROLLING UPGRADE] Please login using weka user login on host $2."
else
  GOOD " [WEKA USER LOGIN TEST ROLLING UPGRADE] Weka user login successful on host $2."
fi
}

function weka_agent_service() {
  if [ "$1" -eq 0 ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [WEKA AGENT SERVICE] Weka Agent Serivce is running on host $2."
    fi
  else
    BAD " [WEKA AGENT SERVICE] Weka Agent Service is NOT running on host $2. Skipping checks."
    return 1
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
    BAD " [WEKA CONTAINER STATUS] Unable to determine container status on Host $2. Skipping checks."
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
    BAD " [WEKA CONTAINER DISABLED STATUS] Unable to determine container status on Host $2."
  fi

  if [ "$1" == "True" ]; then
    BAD " [WEKA CONTAINER DISABLED STATUS] Weka local container is disabled on Host $2, please enable using weka local enable."
  else
    if [[ ! $XCEPT ]] ; then GOOD " [WEKA CONTAINER DISABLED STATUS] Weka local container is running Host $2."
    fi
  fi
}

# Check for any SMB containers, these may need stopping BEFORE upgrade.
function smb_check() {
  if [ -z "$1" ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING SMB/NFS-W RESOURCES] NO SMB/NFS-W containers found on Host $2."
    fi
  else
    WARN " [CHECKING SMB/NFS-W RESOURCES] Found SMB/NFS-W resources on Host $2. Recommend stopping SMB/NFS-W container before upgrade on this backend."
  if [ "$3" -gt 10000000 ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING AVAILABLE MEMORY] Sufficient memory found on $2."
    fi
  else
    WARN "  [CHECKING AVAILABLE MEMORY] Insufficient memory found on Host $2 running SMB/NFS-W, minimum required 10GB."
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

LOGSDIR1='/opt/weka'
LOGSDIR2='/opt/weka/logs'
DATADIR="${LOGSDIR1}/data/default_${WEKAVERSION}"
TOTALHOSTS=$(weka cluster host --no-header | wc -l)
function freespace_backend() {
  if [ -z "$1" ] || [ -z "$2" ] || [ -z "$4" ]; then
    BAD " [FREE SPACE CHECK] Unable to determine free space on Host $3."
    return 1
  fi

  if [ "$1" -lt "$HOSTSPACE1" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has less than recommended free space of ~$(($1 / 1000))GB in $LOGSDIR1."
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786."
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 has recommended free space of ~$(($1 / 1000))GB in $LOGSDIR1."
      fi
  fi

  if [[ "$TOTALHOSTS" -ge "$LARGE_CLUSTER" && "$2" -lt "$HOSTSPACE2" ]]; then
    BAD " [FREE SPACE CHECK] Host $3 has less than recommended free space of $2MB in $LOGSDIR2."
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786."
    return 1
  fi

  if [ "$2" -lt "$HOSTSPACEMIN" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $2MB in $LOGSDIR2."
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786"
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 has Recommended Free Space of $2MB in $LOGSDIR2."
    fi
  fi

  if [ "$4" -gt "$DATASPACE" ]; then
    BAD " [FREE SPACE CHECK] Host $3 data directory is too large current size $4MB expected size $DATASPACE."
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 data directory $DATADIR size ok current size $4MB."
    fi
  fi
}

# Check for any Weka filesystems mountd on /weka
function weka_mount() {
  if [ "$1" -eq 0 ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING WEKA MOUNT] NO Weka file systems mounted on Host $2."
    fi
  else
    BAD " [CHECKING WEKA MOUNT] Weka mounts found on Host $2 unmount prior to upgrade."
  fi
}

# Check for any invalid IP addresses in Weka resources. See https://wekaio.atlassian.net/wiki/spaces/MGMT/pages/1503330580/Cleaning+up+backend+IPs+on+systems+upgraded+to+3.8
function weka_ip_cleanup() {
  if [ "$1" -eq 0 ]; then
    if [[ ! $XCEPT ]] ; then GOOD " [CHECKING IP WEKA RESOURCES] $1 invalid IP addresses found in Weka resources on Host $2."
    fi
  else
    BAD " [CHECKING IP WEKA RESOURCES] $1 Invalid IP addresses in weka resources found on Host $2. Need to run update_backend_ips.py on this backend."
    WARN "  [CHECKING IP WEKA RESOURCES] https://wekaio.atlassian.net/wiki/spaces/MGMT/pages/1503330580/Cleaning+up+backend+IPs+on+systems+upgraded+to+3.8."
  fi
}

function freespace_client() {
  if [ -z "$1" ]; then
    BAD " [FREE SPACE CHECK] Unable to Determine Free Space on Host $3."
    return 1
  fi

  if [ "$1" -lt "$CLIENTSPACE1" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $(($1 / 1000))GB in $LOGSDIR1."
    WARN " [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786."
  else
    if [[ ! $XCEPT ]] ; then GOOD " [FREE SPACE CHECK] Host $3 has Recommended Free Space of $(($1 / 1000))GB in $LOGSDIR1."
    fi
  fi

  if [[ "$TOTALHOSTS" -ge "$LARGE_CLUSTER" && "$2" -lt "$CLIENTSPACE2" ]]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $2MB in $LOGSDIR2."
    WARN " [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786."
    return 1
  fi

  if [ "$2" -lt "$CLIENTSPACEMIN" ]; then
    BAD " [FREE SPACE CHECK] Host $3 has Less than Recommended Free Space of $2MB in $LOGSDIR2."
    WARN "  [REDUCE TRACES CAPACITY & INCREASE DIRECTORY SIZE] https://stackoverflow.com/c/weka/questions/1785/1786#1786."
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


S3CLUSTERSTATUS=$(weka s3 cluster -J | awk '/"active":/{print $2}' | tr -d ",")
if [ "$S3CLUSTERSTATUS" == true ]; then
  if [[ "$MAJOR" -lt 4 ]]; then
  NOTICE "VERIFY ETCD HEALTH"
    S3CLUSTERETCDHEALTH=$(sudo weka local exec -C s3 etcdctl endpoint health --cluster -w table)
    if [ -z $(echo "$S3CLUSTERETCDHEALTH" | grep false) ]; then
      GOOD "ETCD cluster health ok"
    else
      BAD "ETCD cluster health NOT ok"
      BAD "${S3CLUSTERETCDHEALTH}"
    fi
  fi

  NOTICE "VERIFYING S3 CONTAINER STATUS"
  S3HOSTIP=$(weka cluster host $(weka s3 cluster status | grep -o '[0-9]\+' | tr '\n' " ") --no-header -o ips)
    for s3host in ${S3HOSTIP}; do
      CURHOSTNAME=$(weka cluster host --no-header -o hostname,ips | grep -w "${s3host}" | awk '{print $1}' | sort -u)
      if [[ "$MAJOR" -eq 3 ]] && [[ "$WEKAMINOR1" -eq 14 ]] || [[ "$MAJOR" -ge 4 ]]; then
        CURRHOSTID=$(weka cluster host --no-header -o id,ips,container | grep -i default | grep -w "${s3host}" | awk '{print $1}' | sort -u)
      else
        CURRHOSTID=$(weka cluster host --no-header -o id,ips,containerName | grep -i default | grep -w "${s3host}" | awk '{print $1}' | sort -u)
      fi
      S3CONRUN=$("$SSH" "${s3host}" weka local ps --no-header -o name,state | awk '/s3/ {print $2}');
      S3CONDISABLE=$("$SSH" "${s3host}" weka local ps --no-header -o name,disabled | awk '/s3/ {print $2}')
      MINIOSTATUS=$(weka s3 cluster status | awk -F: '/HostId<'"${CURRHOSTID}"'>/ {print $2}' | grep Not)
      if [ -z "$S3CONRUN" ]; then
        BAD "Unable to determine s3 container status on Host ${CURHOSTNAME}."
      elif [ "$S3CONRUN" == "Running" ] && [ "$S3CONDISABLE" == "False" ] && [ -z "$MINIOSTATUS" ]; then
        GOOD "Host ${CURHOSTNAME} s3 container status running, is enabled and Minio is ready."
      elif [ "$S3CONRUN" == "Running" ] && [ "$S3CONDISABLE" == "False" ] && [ ! -z "$MINIOSTATUS" ]; then
        WARN "Host ${CURHOSTNAME} s3 container status running, is enabled but Minio is NOT ready."
      elif [ "$S3CONRUN" == "Running" ] && [ "$S3CONDISABLE" == "True" ] && [ -z "$MINIOSTATUS" ]; then
        WARN "Host ${CURHOSTNAME}s3 container status running, but is disabled and Minio is NOT ready."
      elif [ "$S3CONRUN" == "Running" ] && [ "$S3CONDISABLE" == "True" ] && [ ! -z "$MINIOSTATUS" ]; then
        WARN "Host ${CURHOSTNAME} s3 container status running, but is disabled and Minio is ready."
      elif [ "$S3CONRUN" == "Stopped" ] && [ "$S3CONDISABLE" == "True" ]; then
        WARN "Host ${CURHOSTNAME} s3 container status stopped but is disabled and Minio is Not ready."
      elif [ "$S3CONRUN" == "Stopped" ] && [ "$S3CONDISABLE" == "False" ]; then
        WARN "Host ${CURHOSTNAME} s3 container status stopped but its enabled and Minio is Not ready."
      fi
    done
fi

BACKEND=$(weka cluster host -b --no-header -o ips | awk -F, '{print $1}' | sort -u)
CLIENT=$(weka cluster host -c --no-header -o ips | awk -F, '{print $1}')

function backendloop() {
local CURHOST REMOTEDATE WEKACONSTATUS RESULTS1 RESULTS2 UPGRADECONT MOUNTWEKA SMBCHECK
  CURHOST=$(weka cluster host --no-header -o hostname,ips | grep -w "$1" | awk '{print $1}' | sort -u)
  NOTICE "VERIFYING SETTINGS ON BACKEND HOST $CURHOST"
  check_ssh_connectivity "$1" "$CURHOST" || return

  ID=$($SSH "$1" grep -w ID /etc/os-release | awk -F= '{print $2}' | tr -d '"')
  VERSION_ID=$($SSH "$1" grep -w VERSION_ID /etc/os-release | awk -F= '{print $2}' | tr -d '"')
  VERSION=$($SSH "$1" grep -w VERSION /etc/os-release | awk -F= '{print $2}' | tr -d '"')
  NAME=$($SSH "$1" grep -w NAME /etc/os-release | awk -F= '{print $2}' | tr -d '"')
  os_check "$ID" "$VERSION_ID" "$VERSION" "$NAME"

  REMOTEDATE=$($SSH "$1" "date --utc '+%s'")
  diffdate "$REMOTEDATE" "$CURHOST"

  RESULTS1=$($SSH "$1" df -m "$LOGSDIR1" | awk '{print $4}' | tail -n +2 2>/dev/null)
  RESULTS2=$($SSH "$1" df -m "$LOGSDIR2" | awk '{print $4}' | tail -n +2 2>/dev/null)
  RESULTS3=$($SSH "$1" du -sm "$DATADIR" | cut -f1 2>/dev/null)

  freespace_backend "$RESULTS1" "$RESULTS2" "$CURHOST" "$RESULTS3"

  MOUNTWEKA=$($SSH "$1" "mount -t wekafs | wc -l")
  weka_mount "$MOUNTWEKA" "$CURHOST"

  WEKAAGENTSRV=$($SSH "$1" sudo service weka-agent status > /dev/null ; echo $?)
  weka_agent_service "$WEKAAGENTSRV" "$CURHOST" || return

  WEKACONSTATUS=$($SSH "$1" weka local ps --no-header -o name,running | awk '/default/ {print $2}')
  weka_container_status "$WEKACONSTATUS" "$CURHOST" || return

  CONDISABLED=$($SSH "$1" weka local ps --no-header -o name,disabled | awk '/default/ {print $2}')
  weka_container_disabled "$CONDISABLED" "$CURHOST"

  SMBCHECK=$($SSH "$1" weka local ps | grep -E 'samba|ganesha')
  AMEMORY=$($SSH "$1" sudo cat /proc/meminfo | awk '/MemAvailable:/ {print $2}')
  smb_check "$SMBCHECK" "$CURHOST" "$AMEMORY"

  UPGRADECONT=$($SSH "$1" weka local ps --no-header -o name,running | awk '/upgrade/ {print $2}')
  upgrade_container "$UPGRADECONT" "$CURHOST"

  if [ ! -z "$AWS" ]; then
    IPCLEANUP=$($SSH "$1" sudo weka local resources -C default -J | grep -c -E -o '([0]{1,3}[\.]){3}[0]{1,3}')
     weka_ip_cleanup "$IPCLEANUP" "$CURHOST"
  else
    IPCLEANUP=$($SSH "$1" sudo weka local resources -C default -J | grep -c -E -o '([0]{1,3}[\.]){3}[0]{1,3}')
     weka_ip_cleanup "$IPCLEANUP" "$CURHOST"
  fi

  if [ ! -z "$ROLL" ]; then
  WEKALOGIN=$($SSH "$1" "weka cluster nodes 2>&1 | awk '/error:/'")
  weka_user_login "$WEKALOGIN" "$CURHOST"
  fi

  if [ ! -z "$ROLL" ]; then
  check_jq "$1" "$CURHOST"
  fi

  if [ "$XCEPT" ];then
    WARN "Backend host checks completed please see logs for details $LOG."
  fi
}

function clientloop() {
local CURHOST REMOTEDATE WEKACONSTATUS RESULTS1 RESULTS2 UPGRADECONT MOUNTWEKA
  CURHOST=$(weka cluster host --no-header -o hostname,ips | grep -w "$1" | awk '{print $1}')
  NOTICE "VERIFYING SETTINGS ON CLIENTs HOST $CURHOST"
  check_ssh_connectivity "$1" "$CURHOST" || return

  ID=$($SSH "$1" grep -w ID /etc/os-release | awk -F= '{print $2}' | tr -d '"') ;
  VERSION_ID=$($SSH "$1" grep -w VERSION_ID /etc/os-release | awk -F= '{print $2}' | tr -d '"')
  VERSION=$($SSH "$1" grep -w VERSION /etc/os-release | awk -F= '{print $2}' | tr -d '"')
  NAME=$($SSH "$1" grep -w NAME /etc/os-release | awk -F= '{print $2}' | tr -d '"')
  os_check "$ID" "$VERSION_ID" "$VERSION" "$NAME"

  RESULTS1=$($SSH "$1" df -m "$LOGSDIR1" | awk '{print $4}' | tail -n +2)
  RESULTS2=$($SSH "$1" df -m "$LOGSDIR2" | awk '{print $4}' | tail -n +2)
  freespace_client "$RESULTS1" "$RESULTS2" "$CURHOST"

  WEBTEST=$($SSH "$1" curl -sL -w "%{http_code}" "http://www.google.com/" -o /dev/null)
  client_web_test "$WEBTEST"

  REMOTEDATE=$($SSH "$1" "date --utc '+%s'")
  diffdate "$REMOTEDATE" "$CURHOST"

  MOUNTWEKA=$($SSH "$1" "sudo mountpoint -qd /weka/ | wc -l")
  weka_mount "$MOUNTWEKA" "$CURHOST"

  WEKAAGENTSRV=$($SSH "$1" sudo service weka-agent status > /dev/null ; echo $?)
  weka_agent_service "$WEKAAGENTSRV" "$CURHOST" || return

  WEKACONSTATUS=$($SSH "$1" sudo weka local ps --no-header -o name,running | awk '/client/ {print $2}')
  weka_container_status "$WEKACONSTATUS" "$CURHOST" || return

  UPGRADECONT=$($SSH "$1" sudo weka local ps --no-header -o name,running | awk '/upgrade/ {print $2}')
  upgrade_container "$UPGRADECONT" "$CURHOST"

  if [ "$XCEPT" ];then
    WARN "Client checks completed please see logs for details $LOG."
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
  NOTICE "SKIPPING CLIENTS UPGRADE CHECKS"
else
  for ip in ${CLIENT}; do
    clientloop "$ip" || continue
  done
fi
}

main "$@"
