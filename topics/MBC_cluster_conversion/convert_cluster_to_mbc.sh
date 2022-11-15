#!/bin/bash

# docs are here: https://www.notion.so/SBC-to-MBC-convertor-3de4a1be68124a08a6d694da7fcaeeea
#version=1.0

# Colors
export NOCOLOR="\033[0m"
export CYAN="\033[0;36m"
export YELLOW="\033[1;33m"
export RED="\033[0;31m"
export GREEN="\033[1;32m"
export BLUE="\033[1;34m"

DIR='/tmp'
SSH="/usr/bin/ssh -o LogLevel=ERROR -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
LOG="./mbc_divider.log"
FILE="$DIR/mbc_divider_script.py"
RES_GEN_FILE="$DIR/resources_generator.py"
CLIENTHOST="$DIR/weka_client_host.txt"
WEKA_AUTH_DIR=~/.weka
WEKA_AUTH_FILE=$WEKA_AUTH_DIR/auth-token.json
STOP_FILE="./stop_file"
SKIP_FAILED=0
ALERTS_SKIP=0
SILENT=0
SKIP_VERSION_CHECK=0
usage()
{
cat <<EOF
Usage: [-f will allow script run even if backup resource file exists.]
Usage: [-a will allow to run the script with active alerts.]
Usage: [-s skip failed hosts.]
Usage: [-d override drain grace period in seconds.]
Usage: [-b to perform conversion on a single host, input should be a valid ip.]
Usage: [-l log file will be saved to this location instead of current dir.]
Usage: [-i path to ssh identity file.]
Usage: [-h show this help string.]

This script allow the conversion of regular weka architecture to multiple backend architecture
OPTIONS:
  -f force override of backup resources file if exist
  -a run with active alerts
  -s skip failed hosts
  -d override drain grace period for s3 in seconds
  -b to perform conversion on a single host
  -l log file will be saved to this location instead of current dir
  -D assign drive dedicated cores (use only for on-prem deployment, this will override pinned cores)
  -F assign frontend dedicated cores (use only for on-prem deployment, this will override pinned cores)
  -C assign compute dedicated cores (use only for on-prem deployment, this will override pinned cores)
  -m override max memory memory assignment after conversion (value should be given in GiB
  -i path to ssh identity file.
  -h show this help string
EOF
exit
}

while getopts "hfasd:b:Sl:VC:D:F:m:i:kO" o; do
    case "${o}" in
        f)
            FORCE='--force'
            echo "Option -f will allow script to run event if backup resource file exists"
            ;;
        a)
            ALERTS_SKIP=1
            echo "Option -a will allow to run the script with active alerts"
            ;;
        s)
            SKIP_FAILED=1
            echo "Option -s will skip failed host"
            ;;
        d)
            DRAIN_TIMEOUT='--s3-drain-gracetime '$OPTARG' '
            echo "Option -d set drain grace period to $OPTARG second"
            ;;
        b)
            BACKEND=${OPTARG}
            echo "Option -b will run conversion on $BACKEND"
            ;;
        S)
            SILENT=1
            ;;
        l)
            LOG=${OPTARG}
            echo "Log path will be $LOG"
            ;;
        V)
            SKIP_VERSION_CHECK=1
            echo "Option -V will skip version check"
            ;;
        D)
            DRIVE_CORES='--drive-dedicated-cores '$OPTARG
            echo "Option -D set drive cores to $OPTARG"
            ;;
        C)
            COMPUTE_CORES='--compute-dedicated-cores '$OPTARG
            echo "Option -C set compute cores to $OPTARG"
            ;;
        F)
            FRONTEND_CORES='--frontend-dedicated-cores '$OPTARG
            echo "Option -F set frontend cores to $OPTARG"
            ;;
        m)
            LIMIT_MEMORY='--limit-maximum-memory '$OPTARG
            echo "Option -m set limit maximum memory to  $OPTARG GiB"
            ;;
        k)
            KEEP_S3_UP_FLAG='--keep-s3-up '$OPTARG
            KEEP_S3_UP=true
            echo ""
            ;;
        i)
            SSH_IDENTITY=" -i $OPTARG"
            SSH="$SSH $SSH_IDENTITY"
            echo "Option -i set ssh identity file to $OPTARG"
            ;;
        O)
            FORCE_CONTINUE_WITHOUT_REAL_DRAIN="--dont-enforce-drain"
            echo "Option -O dont enforce drain"
            ;;
        h)
            usage
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
        printf "${CYAN}""\r%-28s" " Sleeping for $ii seconds ..."
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
    (( P_CNT=CNT-1 ))
  if [ -f "${f}"."${limit}" ]; then
    rm "${f}"."${limit}"
  fi

# Renames logs .1 through .3
while [[ $CNT -ne 1 ]] ; do
  if [ -f "${f}"."${P_CNT}" ]; then
    mv "${f}"."${P_CNT}" "${f}"."${CNT}"
  fi
  (( CNT=CNT-1 ))
  (( P_CNT=P_CNT-1 ))
done

# Renames current log to .1
mv "$f" "${f}".1
echo "" > "$f"
fi
}

function NOTICE() {
echo -e "\n${CYAN}$1${NOCOLOR}"
logit "[$1]"
}

function GOOD() {
echo -e "${GREEN}$1${NOCOLOR}"
logit [ SUCCESS ] "$1"
}

function WARN() {
echo -e "${YELLOW}$1${NOCOLOR}"
logit [ WARN ] "$1"
}

function BAD() {
echo -e "${RED}$1${NOCOLOR}"
logit [ FAILED ] "$1"
}

if [ "$EUID" -ne 0 ]; then
  SUDO="sudo "
  NOTICE "WE ARE NOT ROOT, VERIFYING PASSWORDLESS SUDO"
  CAN_SUDO=$(sudo -n uptime 2>&1 | grep "load" | wc -l)
  if [ "$CAN_SUDO" -ne 1 ]; then
    BAD "SUDO IS NOT PASSWORDLESS, RUN AS ROOT"
    exit 1
  fi
fi

if [ ! -e $LOG ]; then
  $SUDO touch $LOG
fi

if [ -w $LOG ]; then
  NOTICE "LOG FILE WRITABLE"
  else
  BAD "CAN'T WRITE TO LOG FILE, PLEASE EXECUTE SCRIPT FROM A DIFFERENT PWD"
  exit 1
fi

NOTICE "VERIFYING WEKA AGENT"
WEKAVERIFY=$($SUDO lsmod | grep -i weka)
if [ -z "$WEKAVERIFY" ]; then
  BAD "Weka is NOT installed on host or the container is down, cannot continue."
  exit 1
fi
WEKA_VERSION=$(weka version current)
NOTICE "VERIFYING WEKA VERSION"
  MAJOR=$(echo "$WEKA_VERSION" | cut -d "." -f1)
  WEKAMINOR1=$(echo "$WEKA_VERSION" | cut -d "." -f2)
  WEKAMINOR2=$(echo "$WEKA_VERSION" | cut -d "." -f3 | tr -dc '0-9')
if [ "$MAJOR" -eq 4 ] || [[ "$MAJOR" -eq 3 && "$WEKAMINOR1" -ge 14 && "$WEKAMINOR2" -ge 2 ]] || [ "$SKIP_VERSION_CHECK" -eq "1" ]; then
  GOOD "Supported Weka version $WEKA_VERSION"
  else
  BAD "Unsupported Weka version, this script support version 3.14.3 and up, current version $WEKA_VERSION"
  exit 1
fi

NOTICE "VERIFY USER IS LOGGED IN"
WEKALOGIN=$(weka user whoami -J 2>&1 | awk '/"role"/ {gsub("\"","");gsub(",",""); print $2;}')
if [ "$WEKALOGIN" != "ClusterAdmin" ]; then
  BAD "Weka user is either not a ClusterAdmin or weka is not logged in. Please login using 'weka user login' with an admin user"
  exit 1
else
  GOOD "Weka user login successful. has clusterAdmin role "
fi

NOTICE "WEKA IDENTIFIED"
CLUSTER=$(weka status | grep cluster | awk 'NR==1 {print $2}')
UUID=$(weka status | grep cluster | awk 'NR==1 {print $3}')
CLUSTERSTATUS=$(weka status | grep status | head -n -1 | cut -d':' -f2)
IOSTATUS=$(weka status | grep status | tail -n +2 | cut -d':' -f2)
BACKENDIP=$(weka cluster host -b --no-header -o ips,status | awk '/UP/ {print $1}' | tr -d ',' | uniq)
weka cluster host -c --no-header -o hostname,status | awk '/UP/ {print $1}' > $CLIENTHOST
GOOD "Working on CLUSTER: $CLUSTER UUID: $UUID STATUS:${CLUSTERSTATUS}${IOSTATUS}."

#verify local container status otherwise commands will fail
NOTICE "VERIFYING WEKA LOCAL CONTAINER STATUS"
CONSTATUS=$($SUDO weka local ps --no-header -o name,running | grep -i default | awk '{print $2}')
if [ "$CONSTATUS" == "False" ]; then
  BAD "Weka local container is down cannot continue."
  exit
else
  GOOD "Weka local container is running."
fi

if [ "$KEEP_S3_UP" == true ]; then
  WARN "Enabling changing nodes role"
  weka debug jrpc config_override_key key=clusterInfo.allowChangingActiveHostNodes value=true > /dev/null
fi
NOTICE "CHECKING FOR ANY ALERTS"
WEKAALERTS="$(weka alerts)"
if [ "$WEKAALERTS" != "" ]; then
  WARN "$WEKAALERTS Weka alerts present, for additional details see log ${LOG}."
  logit "\n$(weka alerts)"
  if [ $ALERTS_SKIP -ne 1 ]; then
    WARN "There are un muted alerts, you can either mute the alerts or run with -a "
    exit
  fi
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
  $SSH -q -o BatchMode=yes -o ConnectTimeout=5 $IP exit
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
if [ "$EUID" -ne 0 ]; then
  SUDO="sudo "
fi

NOTICE "VERIFYING $FILE PERMISSIONS"
FPERM=$(stat -c "%a %n" $FILE | cut -c1-3)
if [ "$FPERM" != 775 ]; then
  NOTICE "MAKING $FILE EXECUTABLE"
  $SUDO chmod 775 $FILE
else
  GOOD "File Permission are set correctly"
fi

NOTICE "VERIFYING $RES_GEN_FILE PERMISSIONS"
FPERM=$(stat -c "%a %n" $RES_GEN_FILE | cut -c1-3)
if [ "$FPERM" != 775 ]; then
  NOTICE "MAKING $RES_GEN_FILE EXECUTABLE"
  $SUDO chmod 775 $RES_GEN_FILE
else
  GOOD "File Permission are set correctly"
fi
NOTICE "DISTRIBUTING FILE TO HOST $1"
echo "scp $SSH_IDENTITY -p $FILE $1:$DIR > /dev/null"
scp $SSH_IDENTITY -p $FILE $1:$DIR > /dev/null
if [ $? -ne 0 ]; then
  BAD "Unable to SCP $FILE to $1"
  WARN "Skipping $1"
  return 1
else
  GOOD "$FILE transferred successfully"
fi

scp $SSH_IDENTITY -p $RES_GEN_FILE $1:$DIR > /dev/null
if [ $? -ne 0 ]; then
  BAD "Unable to SCP @RES_GEN_FILE to $1"
  WARN "Skipping $1"
  return 1
else
  GOOD "$RES_GEN_FILE transferred successfully"
fi
if [ -f "$WEKA_AUTH_FILE" ]; then
  $SSH $1 mkdir -p $WEKA_AUTH_DIR
  scp $SSH_IDENTITY -p $WEKA_AUTH_FILE $1:$WEKA_AUTH_FILE > /dev/null
  if [ $? -ne 0 ]; then
      BAD "Unable to SCP @WEKA_AUTH_FILE to $1"
      WARN "Skipping $1"
      return 1
  else
      GOOD "$WEKA_AUTH_FILE transferred successfully"
  fi
fi

NOTICE "======================================
EXECUTING CONVERSION TO MBC ON HOST $1
======================================"
$SSH "$1" "$DIR/mbc_divider_script.py $AWS $FORCE $DRAIN_TIMEOUT $DRIVE_CORES $COMPUTE_CORES $FRONTEND_CORES $LIMIT_MEMORY $KEEP_S3_UP_FLAG $FORCE_CONTINUE_WITHOUT_REAL_DRAIN" 2>&1 | tee -a ${LOG}
if [ "${PIPESTATUS[0]}" != "0" ]; then
    BAD "UNABLE TO CONVERT HOST $1"
    return 1
  else
    GOOD "HOST $1 WAS SUCCESSFULLY CONVERTED TO MBC"
  fi

NOTICE "VERIFYING REBUILD STATUS COMPLETE"
WARN "Waiting for rebuild to complete please standby..."
  while : ; do
    REBUILDSTATUS="$(weka status rebuild -J | awk '/progressPercent/ {print $2}' | tr -d ',')"
    WEKASTATUS="$(weka status | grep 'status: OK' | awk '/status:/ {print $2}')"
    if [ "$SILENT" == 0 ]; then
      echo -ne "$REBUILDSTATUS%\\r"
    fi
    if [ "$REBUILDSTATUS" == 0 ] || [ "$WEKASTATUS" == OK ]; then
      GOOD "Rebuild complete.   "
      break
    fi
    sleep 20
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
  return 0
}

BKHOSTNAME=$(weka cluster host -b --no-header -o hostname,status | awk '/UP/ {print $1}')

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


main() {
NOTICE "STARTING CLUSTER WIDE conversion"
if [ -z "$BACKEND" ]; then
  for HOST in ${BACKENDIP}; do
    if [ -f $STOP_FILE ]; then
      WARN "STOP FILE DETECTED, CLUSTER WIDE CONVERSION TO MBC WILL STOP, DELETE FILE AND RERUN TO CONTINUE"
      exit 0
    fi
    _distribute "$HOST"
    ret_val=$?
    if [ "$ret_val" -ne '0' ]; then
      if [ "$SKIP_FAILED" -ne '1' ]; then
        WARN "FAILED converting $HOST, exiting. For more information refer to the log at $LOG"
        exit 1
      fi
    fi
  done
  NOTICE "Done converting cluster to MBC"
else
  _distribute "$BACKEND"
  ret_val=$?
  if [ "$ret_val" -ne '0' ]; then
    if [ "$SKIP_FAILED" -ne '1' ]; then
      WARN "FAILED converting $BACKEND, exiting. For more information refer to the log at $LOG"
      exit 1
    fi
  fi
  NOTICE "Done converting $BACKEND to MBC"
fi
weka debug jrpc config_override_key key=clusterInfo.allowChangingActiveHostNodes value=false > /dev/null
weka status
}
main "$@"
