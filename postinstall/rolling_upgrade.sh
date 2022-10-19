#!/bin/bash

set -e

CLUSTER_RETURN_TO_HEALTHY_TIMEOUT=3600
MINIMAL_VERSION_FOR_NAMED_DATA_DIR=3.5
USER_DOMAIN=
FORCE=0
__cache_file=$(mktemp)
rm -rf "$__cache_file"
trap 'rm -rf $__cache_file' EXIT

export GRAY="\033[1;30m"
export LIGHT_GRAY="\033[0;37m"
export CYAN="\033[0;36m"
export LIGHT_CYAN="\033[1;36m"
export PURPLE="\033[1;35m"
export YELLOW="\033[1;33m"
export LIGHT_RED="\033[1;31m"
export NO_COLOUR="\033[0m"

usage() {
  cat <<DELIM
Usage: rolling_upgrade.sh BOOTSTRAP_MACHINE VERSION [options]
By default, only backend servers are upgraded. However, additional roles can be upgraded as well if specified by flags

Optional arguments:
    -d|--domain                     Expect different domain, default wekalab.io
    -t|--cluster-healthy-timeout    Wait for X seconds for cluster to become healthy after weka restart on a single machine, default $CLUSTER_RETURN_TO_HEALTHY_TIMEOUT
    -l|--include-legacy-clients     Include LEGACY clients
    -s|--include-stateless-clients  Include STATELESS clients
    -a|--include-all-clients        Include also ALL types of frontends (stateless / legacy clients, NFS/SMB gateways etc.), implies -l , -s

    -x|--dry-run                    Do not perform any operation actually, only dry-run to test the script is working

    --force                         Don't ask for any confirmations
DELIM
}

check_jq_installed() {
  log_message DEBUG Checking for existence of jq package...
  if ! command -v jq &>/dev/null; then
    log_message ERROR "'jq' executable was not found. Please install jq and rerun the script (refer to your Linux distribution documentation)"
    exit 1
  fi
}

get_rebuild_progress() {
  # returns 0 if no rebuild in progress on cluster
  local MACHINE=$1
  ssh "root@$MACHINE" weka status | grep -ic "rebuild"
}

check_all_backends_up() {
  # returns 0 if all backends up
  local STATUS ACTIVE TOTAL
  STATUS="$(jq .hosts.backends <<< "$@")"
  TOTAL=$(jq -r .total <<< "$STATUS")
  ACTIVE=$(jq -r .active <<< "$STATUS")
  if (( ACTIVE == TOTAL )); then
    log_message DEBUG "$ACTIVE/$TOTAL backends on cluster are up"
  else
    log_message WARNING "$ACTIVE/$TOTAL backends on cluster are up"
    return 1
  fi
}

check_all_drives_up() {
  # returns 0 if all drives up
  local STATUS ACTIVE TOTAL
  STATUS="$(jq .drives <<< "$@")"
  TOTAL=$(jq -r .total <<< "$STATUS")
  ACTIVE=$(jq -r .active <<< "$STATUS")
  if (( ACTIVE == TOTAL )); then
    log_message DEBUG "$ACTIVE/$TOTAL drives on cluster are up"
  else
    log_message WARNING "$ACTIVE/$TOTAL drives on cluster are up"
    return 1
  fi
}

check_all_ionodes_up() {
  # returns 0 if all backends up
  local STATUS ACTIVE TOTAL
  STATUS="$(jq .io_nodes <<< "$@")"
  TOTAL=$(jq -r .total <<< "$STATUS")
  ACTIVE=$(jq -r .active <<< "$STATUS")
  if (( ACTIVE == TOTAL )); then
    log_message DEBUG "$ACTIVE/$TOTAL IoNodes on cluster are up"
  else
    log_message WARNING "$ACTIVE/$TOTAL IoNodes on cluster are up"
    return 1
  fi
}

check_no_rebuild() {
  local STATUS
  STATUS="$(jq -r .rebuild.progressPercent <<< "$@")"
  log_message DEBUG "Rebuild percentage: $STATUS"
  [[ $STATUS == 0 ]] || return 1
}

check_cluster_healthy() {
  # returns 0 if cluster is in healthy state and no rebuild is in progress
  local MACHINE STATUS STATUS_JSON
  MACHINE="$1"
  STATUS_JSON="$(_get_weka_status "$MACHINE")"
  check_all_backends_up "$STATUS_JSON" &&  \
  check_all_drives_up "$STATUS_JSON" &&  \
  check_all_ionodes_up "$STATUS_JSON" &&  \
  check_no_rebuild "$STATUS_JSON" &&  \
  return 0 || \
  return 1
}

wait_cluster_healthy() {
  # waits for maxumum of $CLUSTER_RETURN_TO_HEALTHY_TIMEOUT for the cluster to enter healthy state
  local MACHINE=$1
  first_time=$(date +%s)
  log_message INFO "Ensuring cluster in healthy state (against $MACHINE), will wait up to $CLUSTER_RETURN_TO_HEALTHY_TIMEOUT seconds"
  while (($(date +%s) - first_time <= CLUSTER_RETURN_TO_HEALTHY_TIMEOUT)); do
    check_cluster_healthy "$MACHINE" && log_message INFO Cluster is healthy && return 0
    sleep 3
  done
  log_message CRITICAL "Failed to enter valid state after $CLUSTER_RETURN_TO_HEALTHY_TIMEOUT"
  return 1
}

ts() {
  local LINE
  while read LINE; do
    echo -e "$(date "+$*") $LINE"
  done
}

log_message() {
  # just add timestamp and redirect logs to stderr
  local LEVEL COLOR
  [[ ${1^^} =~ TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|CRITICAL|FATAL ]] && LEVEL="${1^^}" && shift || LEVEL="INFO"

  case $LEVEL in
  DEBUG) COLOR="$LIGHT_GRAY" ;;
  INFO) COLOR="$CYAN" ;;
  NOTICE) COLOR="$PURPLE" ;;
  WARNING | WARN) COLOR="$YELLOW" ;;
  ERROR | CRITICAL) COLOR="$LIGHT_RED" ;;
  esac

  ts "$(echo -e "$COLOR")[%Y-%m-%d %H:%M:%S] $(echo -e "${LEVEL^^}$NO_COLOUR")"$'\t' <<<"$*" | tee -a $LOG_FILE >&2
}

ssh_run() {
  # For commands that actually execute operations
  # In TEST_MODE we will substitute the execution of the command with only printout of the command to be executed
  [[ $TEST_MODE == 1 ]] && log_message DRY RUN: ssh "$@" && return
  command ssh -o LogLevel=ERROR -- "$@"
}

ssh() {
  # For readonly commands, e.g. obtaining statuses, will always be executed, including in TEST_MODE
  command ssh -o LogLevel=ERROR -- "$@"
}

do_machine_upgrade() {
  # performs the upgrade on a single machine, optionally a second machine can be provided to monitor cluster status via it
  local MACHINE CONTAINER_NAMES MONITOR_MACHINE choice
  MACHINE="$1"
  MONITOR_MACHINE=$(get_sibling_machine "$MACHINE")
  log_message DEBUG Obtained sibling machine for "$MACHINE": "$MONITOR_MACHINE"

  CURRENT_VERSION=`ssh "root@$MACHINE" weka version current`
  echo "Current Version is: $CURRENT_VERSION"
  echo "Target Version is:  $TARGET_VERSION"

  if [[ "$CURRENT_VERSION" == "$TARGET_VERSION" ]]; then
      echo "$MACHINE on version $TARGET_VERSION. Skipping"
      return 0
  fi

  if [[ "$FORCE" == "0" ]]; then
    read -p "Continue with machine $MACHINE (y/n/a(allow all)/s(skip machine)?" choice
    case "${choice^^}" in
    Y) echo "Proceeding with $MACHINE" ;;
    N)
      echo "Aborting"
      return 1
      ;;
    A) FORCE=1 ;;
    S)
      echo Skipping machine "$MACHINE"
      return 0
      ;;
    *)
      Aborting
      return 1
      ;;
    esac
  fi

  CONTAINER_NAMES=$(get_machine_containers "$machine")

  log_message NOTICE Upgrading containers "$CONTAINER_NAMES" on machine "$machine"

  log_message NOTICE Current cluster status:
  ssh "root@$MACHINE" weka status | ts '\t'

  log_message DEBUG Stopping Weka on machine "$MACHINE"
  ssh_run "root@$MACHINE" weka local stop || return $?

  for CONTAINER_NAME in $CONTAINER_NAMES; do
    log_message DEBUG Ensuring correct data directory is set up on machine "$MACHINE" on container "$CONTAINER_NAME"
    ensure_container_data_dir_on_machine "$MACHINE" "$CONTAINER_NAME" || return $?
  done

  log_message DEBUG Setting target version on machine "$MACHINE":
  ssh_run "root@$MACHINE" weka version set "$TARGET_VERSION" || return $?

  log_message DEBUG Starting Weka containers on machine "$MACHINE":
  ssh_run "root@$MACHINE" weka local start || return $?

  log_message DEBUG Waiting Weka to become ready on machine "$MACHINE" with containers "$CONTAINER_NAMES" and cluster to return to fully active state
  wait_cluster_healthy "$MONITOR_MACHINE"
  log_message NOTICE Machine "$MACHINE" upgrade completed successfully
}

ensure_container_data_dir_on_machine() {
  # Makes sure that if new version data directory exists on machine, it is backed up
  # and original directory is safely renamed to the new one
  local MACHINE CONTAINER_NAME CURRENT_VERSION TIMESTAMP TARGET_DATA_DIR SOURCE_DATA_DIR

  MACHINE="$1"
  CONTAINER_NAME="$2"
  CURRENT_VERSION="$(get_container_version "$MACHINE" "$CONTAINER_NAME")"
  TIMESTAMP=$(date +%s)

  SOURCE_DATA_DIR="/opt/weka/data/${CONTAINER_NAME}_${CURRENT_VERSION}"
  TARGET_DATA_DIR="/opt/weka/data/${CONTAINER_NAME}_${TARGET_VERSION}"
  if ssh "root@$MACHINE" test -d "$SOURCE_DATA_DIR"; then
    log_message DEBUG "Data directory exists on machine $MACHINE on container $CONTAINER_NAME: $SOURCE_DATA_DIR"
    if ssh "root@$MACHINE" test -d "$TARGET_DATA_DIR"; then
      log_message INFO Found a data directory on machine "$MACHINE" on container "$CONTAINER_NAME" with target version name, Backing it up.
      ssh_run "root@$MACHINE" mv "$TARGET_DATA_DIR" "$TARGET_DATA_DIR.$TIMESTAMP"
      log_message DEBUG "Renaming machine data directory $TARGET_DATA_DIR --> $TARGET_DATA_DIR.$TIMESTAMP"
    fi
    log_message INFO "$MACHINE: Renaming machine data directory $SOURCE_DATA_DIR --> $TARGET_DATA_DIR"
    ssh_run "root@$MACHINE" mv "$SOURCE_DATA_DIR" "$TARGET_DATA_DIR"
  else
    log_message DEBUG Comparing current version $CURRENT_VERSION with MINIMAL_VERSION_FOR_NAMED_DATA_DIR $MINIMAL_VERSION_FOR_NAMED_DATA_DIR
    if ! [[ "$CURRENT_VERSION" < "$MINIMAL_VERSION_FOR_NAMED_DATA_DIR" ]]; then
      # To avoid editing the script on every new version, assume that 3.5 and above always have per version data dir
      log_message ERROR Could not find data directory for container "$CONTAINER_NAME" on "$MACHINE" but it must exist on version "$CURRENT_VERSION"!
      return 1
    fi
  fi
}

normalize_host_name() {
  # returns machine name always as FQDN. accepts both arguments and pipe redirection
  if [[ $* ]]; then
    if [[ $USER_DOMAIN ]]; then
      echo "${*/.$USER_DOMAIN/}.$USER_DOMAIN"
    else
      echo "$@"
    fi
  else
    local line
    while read line; do
      if [[ $USER_DOMAIN != "" ]]; then
        echo "${line/.$USER_DOMAIN/}.$USER_DOMAIN"
      else
        echo "$line"
      fi
    done
  fi
}

_get_cluster_json() {
  # gets all backends from cluster by specifying its name
  # does this by filtering weka cluster host to find only those which are marked as "Dedicated==True"
  # if host.hostname is available, only takes 1 container per hostname.
  # this is crucial for supporting MBC, since the version is set per machine as opposed to per host.
  # if host.hostname is unavailable, falls back to the unfiltered output from 'weka cluster host'.
  if [[ -f "$__cache_file" ]]; then
    cat "$__cache_file"
    return
  fi
  if ping -c1 "$BOOTSTRAP_MACHINE" &>/dev/null; then
    log_message DEBUG Connecting to cluster "$BOOTSTRAP_MACHINE" and obtaining a list of ALL MACHINES
    ssh "root@$BOOTSTRAP_MACHINE" weka cluster host -J | jq 'if all(has("hostname")) then unique_by(.hostname) else . end' > "$__cache_file"
    cat "$__cache_file"
  else
    log_message Could not resolve "$BOOTSTRAP_MACHINE"
    return 1
  fi
}

_get_weka_status() {
  # gets a weka status output in JSON format from the server
  local MACHINE="$1"
  log_message DEBUG Obtaining weka status from machine "$MACHINE"
  ssh "root@$MACHINE" weka status -J
}

get_container_version() {
  local MACHINE="$1"
  local CONTAINER_NAME="$2"
  log_message DEBUG Obtaining status of container "'$CONTAINER_NAME'" on machine "$MACHINE"
  ssh "root@$MACHINE" weka local ps -J |
    jq --arg container_name "$CONTAINER_NAME" '.[] | select(.type == "weka" and .name == $container_name) | .versionName'
}

get_cluster_backends() {
  # returns list of all backends (those on which there are different roles than only frontend installed)
  _get_cluster_json | jq -r '.[] | select(.cores - .frontend_dedicated_cores > 0) | .hostname' | normalize_host_name
}

get_cluster_frontends() {
  # returns list of all servers having only frontend role (all clients + NFS/SMB)
  _get_cluster_json | jq -r '.[] | select(.cores == .frontend_dedicated_cores) | .hostname' | normalize_host_name
}

get_cluster_legacy_clients() {
  # returns list of legacy clients
  _get_cluster_json | jq -r '.[] | select(.cores == .frontend_dedicated_cores) | select(.auto_remove_timeout == null) | .hostname' | normalize_host_name
}

get_cluster_stateless_clients() {
  # returns list of stateless clients
  _get_cluster_json | jq -r '.[] | select(.cores == .frontend_dedicated_cores) | select(.auto_remove_timeout != null) | .hostname' | normalize_host_name
}

get_sibling_machine() {
    # returns a sibling machine on which the weka cluster status will be verified.
    # takes the previous machine related to current one (cyclic)
    local MACHINE=$1 cluster_backends sibling_machine
    cluster_backends=$(get_cluster_backends "$MACHINE") || return 1
    sibling_machine=$(grep -B1  -w "$MACHINE" <<< "$cluster_backends" | grep -v -w "$MACHINE")
    [[ $sibling_machine ]] || sibling_machine=$(tail -1 <<< "$cluster_backends")
    [[ $sibling_machine ]] && echo -n "$sibling_machine" && return
    log_message ERROR Could not find a sibling machine for machine "$MACHINE"
    return 1
}

get_machine_containers() {
    local HOSTNAME=$1
    ssh_run "root@$BOOTSTRAP_MACHINE" weka cluster host -J |
        jq -r --arg hostname "$HOSTNAME" '.[] | select(.hostname == $hostname) | .container_name'
}

prepare_version() {
  local MACHINE=$1
  local CONTAINERS="$(get_machine_containers "$MACHINE" | tr '\n' ' ')"

  log_message INFO Downloading version "$TARGET_VERSION" on machine "$MACHINE"
  ssh_run "root@$MACHINE" "WEKA_DIST_SERVERS='$BOOTSTRAP_MACHINE:14100 $BOOTSTRAP_MACHINE:14000' weka version get '$TARGET_VERSION'" &&
      log_message NOTICE Finished downloading version "$TARGET_VERSION" on machine "$MACHINE" ||
    { log_message ERROR Could not download version "$TARGET_VERSION" on machine "$MACHINE!" && return 1; }

  log_message NOTICE Preparing version "$TARGET_VERSION" on machine "$MACHINE"
  ssh_run "root@$MACHINE" weka version prepare "$TARGET_VERSION" "$CONTAINERS" &&
    log_message NOTICE Finished preparing version "$TARGET_VERSION" on machine "$MACHINE" ||
    { log_message ERROR Could not prepare version "$TARGET_VERSION" on machine "$MACHINE!" && return 1; }
}

main() {
  [[ $# == 0 ]] && usage && exit 1
  check_jq_installed

  while [ $# -ge 1 ]; do
    case $1 in
    -d | --domain)
      [[ $2 ]] && shift && USER_DOMAIN=$1
      shift
      ;;
    -t | --cluster-healthy-timeout)
      [[ $2 ]] && shift && CLUSTER_RETURN_TO_HEALTHY_TIMEOUT=$1
      shift
      ;;
    -l | --include-legacy-clients)
      INCLUDE_LEGACY_CLIENTS=1
      shift
      ;;
    -s | --include-stateless-clients)
      INCLUDE_STATELESS_CLIENTS=1
      shift
      ;;
    -a | --include-all-clients)
      INCLUDE_LEGACY_CLIENTS=1
      INCLUDE_STATELESS_CLIENTS=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -x | --dry-run)
      TEST_MODE=1
      log_message WARNING "Running in dry run mode, no actual operations will be done"
      shift
      ;;
    -h | --help)
      usage
      exit 1
      ;;
    *)
      if [[ ! $BOOTSTRAP_MACHINE ]] ; then
        BOOTSTRAP_MACHINE="$1"
        log_message BOOTSTRAP_MACHINE: "$BOOTSTRAP_MACHINE"
        shift
      elif [[ ! $TARGET_VERSION ]]; then
        TARGET_VERSION=$1
        log_message TARGET_VERSION: "$TARGET_VERSION"
        shift
      else
        log_message Invalid usage!
        usage
        return 1
      fi
      ;;
    esac
  done
  ! { [[ $BOOTSTRAP_MACHINE ]] && [[ $TARGET_VERSION ]]; } && log_message Invalid usage! && usage && return 1

  log_message NOTICE Checking cluster health state before upgrade

  if ! check_cluster_healthy "$(normalize_host_name "$BOOTSTRAP_MACHINE")"; then
    log_message ERROR =========================================
    log_message ERROR Cluster not healthy, cannot upgrade!
    log_message ERROR =========================================
    exit 1
  else
    log_message INFO Cluster is in healthy state, continuing with upgrade...
  fi

  BOOTSTRAP_MACHINE=$(normalize_host_name "$BOOTSTRAP_MACHINE")
  TARGET_MACHINES=$(get_cluster_backends)

  log_message INFO These are the machines to be upgraded:
  echo "$TARGET_MACHINES"        | ts "    BACKEND_MACHINE:     "

  if [[ $INCLUDE_LEGACY_CLIENTS ]]; then
    LEGACY_CLIENTS=$(get_cluster_legacy_clients)
    echo "$LEGACY_CLIENTS"    | ts "    LEGACY_CLIENT:    "
  fi

  if [[ $INCLUDE_STATELESS_CLIENTS ]]; then
    STATELESS_CLIENTS=$(get_cluster_stateless_clients)
    echo "$STATELESS_CLIENTS" | ts "    STATELESS_CLIENT: "
  fi

  log_message NOTICE Preparing version "$TARGET_VERSION" on all machines
  read -p "Skip download version? (y/n)?" choice
    case "${choice^^}" in
    Y) echo "Proceeding with upgrade" ;;
    *)
    for machine in $TARGET_MACHINES $LEGACY_CLIENTS $STATELESS_CLIENTS; do
        log_message DEBUG Ensuring the version "$TARGET_VERSION" exists on machine "$MACHINE"
        prepare_version "$machine" || return $?
    done
    ;;
  esac

  for machine in $TARGET_MACHINES $LEGACY_CLIENTS $STATELESS_CLIENTS; do
    log_message NOTICE --------------------------------------------------
    log_message NOTICE Going to upgrade machine "$machine"
    log_message NOTICE --------------------------------------------------

    if ! do_machine_upgrade "$machine"; then
      log_message ERROR ----------------------------------------------------------------------------
      log_message ERROR do_machine_upgrade on machine "$machine" FAILED, stopping here...
      log_message ERROR ----------------------------------------------------------------------------
      exit 1
    fi
  done
  log_message NOTICE --------------------------------------------------
  log_message NOTICE UPGRADE COMPLETED SUCCESSFULLY!
  log_message NOTICE --------------------------------------------------

}

main "$@"
