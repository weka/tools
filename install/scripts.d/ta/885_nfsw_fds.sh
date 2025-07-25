#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="NFSW FD usage"
JIRA_REFERENCE="WEKAPP-354140"
SCRIPT_TYPE="parallel"

# Maximum number of FDs supported by a frontend node is 500,000
# FD usage can be queried, on a per-backend basis, by using the following command:
# weka local exec -C ganesha -- dbus-send --print-reply --system --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr org.ganesha.nfsd.exportstats.ShowCacheInode
# Number of FDs can be overridden globally via the following command: weka debug config override nfsGaneshaConfig.maxOpenFDs <max FDs>

# Check if we can run weka commands
weka status &> /dev/null
RC=$?

case ${RC} in
    254)
        echo "ERROR: Not able to run weka commands."
        exit 254
        ;;
    127)
        echo "WEKA not found."
        exit 254
        ;;
    41)
        echo "Unable to login to Weka cluster."
        exit 254
        ;;
esac

# Are we on a host w/ a Ganesha container?
if ! weka local status ganesha &> /dev/null; then
    echo "INFO: NFSW not running"
    exit 0
fi

CLUSTERMAXFDS=$(weka debug config show nfsGaneshaConfig.maxOpenFDs || echo -1)
if [[ ${CLUSTERMAXFDS} -eq -1 ]]; then
    echo "INFO: Unable to query NFSW maximum FDs"
    exit 0
fi

LOCALMAXFDS=$(weka local exec -C ganesha -- dbus-send --print-reply --system --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr org.ganesha.nfsd.exportstats.ShowCacheInode | awk '/FSAL/ {flag=1; next} flag && /uint64/ {print $2; flag=0}')
if [[ -z "${LOCALMAXFDS}" ]]; then
    echo "INFO: Unable to query allocated NFSW FDs"
    exit 0
fi

PERCENT=$(awk -v used="$LOCALMAXFDS" -v max="$CLUSTERMAXFDS" 'BEGIN { printf "%.0f", (used / max) * 100 }')

if [[ "$PERCENT" -ge 90 ]]; then
    echo "WARN: Number of allocated NFSW FDs (${LOCALMAXFDS} FDs) is ${PERCENT}% of the max (${CLUSTERMAXFDS} FDs)."
    echo "Recommended Resolution: increase maxOpenFDs to 500000:"
    echo "weka debug config override nfsGaneshaConfig.maxOpenFDs 500000"
    exit 254
else
    echo "INFO: Allocated NFSW FDs (${LOCALMAXFDS} FDs) is ${PERCENT}% of the max (${CLUSTERMAXFDS} FDs)."
    exit 0
fi