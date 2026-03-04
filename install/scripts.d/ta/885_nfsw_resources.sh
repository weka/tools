#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for known NFSW resource issues / limits"
JIRA_REFERENCE=""
SCRIPT_TYPE="parallel"
RETURN_CODE=0

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

# Is IPv6 enabled?
# REF: WEKAPP-546698
if [[ ! -f /proc/net/if_inet6 ]]; then
    echo "WARN: IPv6 disabled on a WEKA host running a ganesha container."
    echo "Disabling IPv6 can impair the NFSW health check when the RPC connection limit is reached."
    echo "Recommended Resolution: enable IPv6 to ensure the NFSW health check is operable."
    RETURN_CODE=254
fi

# Approaching max number of FDs?
CLUSTERMAXFDS=$(weka debug config show nfsGaneshaConfig.maxOpenFDs || echo 200000)
LOCALNUMFDS=$(weka local exec -C ganesha -- dbus-send --print-reply --system --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr org.ganesha.nfsd.exportstats.ShowCacheInode 2>/dev/null | awk '/FSAL/ {flag=1; next} flag && /uint64/ {print $2; flag=0}')
if [[ ! -z "${LOCALNUMFDS}" ]]; then
    PERCENT_FDS=$(awk -v used="$LOCALNUMFDS" -v max="$CLUSTERMAXFDS" 'BEGIN { printf "%.0f", (used / max) * 100 }')

    if [[ "$PERCENT_FDS" -ge 90 ]]; then
        echo "WARN: Number of allocated NFSW FDs (${LOCALNUMFDS} FDs) is ${PERCENT_FDS}% of the max (${CLUSTERMAXFDS} FDs)."
        echo "Recommended Resolution: increase maxOpenFDs to 500000:"
        echo "weka debug config override nfsGaneshaConfig.maxOpenFDs 500000"
        RETURN_CODE=254
    fi
fi

# "Simple" RPC limit check
RPC_MAX=$(grep -oP "(?<=RPC_Max_Connections = )\d+" <<<"$(weka debug config show nfsGaneshaConfig.customGlobalOptions 2>/dev/null)" || true)
RPC_MAX=${RPC_MAX:-1024}
RPC_CURR=$(ss -Hnt sport = :2049 | wc -l)
PERCENT_RPCS=$(awk -v used="$RPC_CURR" -v max="$RPC_MAX" 'BEGIN { printf "%.0f", (used / max) * 100 }')
if [[ "$PERCENT_RPCS" -ge 70 ]]; then
    echo "WARN: The number of NFS RPCS may be approaching 70% or higher of the maxiumum of "$RPC_MAX""
    echo "Recommended Resolution: increase the MAX RPCS:"
    echo "weka nfs custom-options update --global-options \"NFS_CORE_PARAM { RPC_Max_Connections = <NUMBER MAX RPCS>; }\""
    RETURN_CODE=254
fi

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "No NFSW resource issues detected."
fi
exit $RETURN_CODE
