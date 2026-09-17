#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check ethernet link speeds are at maximum advertised"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
REFERENCE="WEKAPP-482528"

RETURN_CODE=0

# Last modified: 2026-09-10
# k8s-client variant: does not use the weka CLI. Every connected ethernet port
# is checked, rather than only those assigned to WEKA containers.

if ! command -v ethtool &> /dev/null ; then
    echo "Unable to locate ethtool; cannot check link speeds"
    exit 0
fi

for DEVICE_PATH in /sys/class/net/* ; do
    NETWORK_DEVICE=${DEVICE_PATH##*/}
    if [[ "$(cat ${DEVICE_PATH}/type 2>/dev/null)" != "1" ]] ; then
        continue
    fi
    # Bonds, VLANs and bridges sit on top of physical ports; the ports themselves are checked directly
    if compgen -G "${DEVICE_PATH}/lower_*" > /dev/null ; then
        continue
    fi
    if [[ "$(cat ${DEVICE_PATH}/carrier 2>/dev/null)" != "1" ]] ; then
        continue
    fi

    ETHTOOL_OUTPUT=$(ethtool ${NETWORK_DEVICE} 2>/dev/null)
    if [[ -z ${ETHTOOL_OUTPUT} ]] ; then
        continue
    fi
    # need to find the fastest shared link speed between "supported" and "advertised" links.
    # there's no /sys/class/net interface to this, and the only kernel interface is ethtool-netlink, as far as I can find:
    #   https://www.kernel.org/doc/html/v5.9/networking/ethtool-netlink.html#linkmodes-get
    # ethtool only recently (v6.11) started supporting json output, so I can't find any other way of doing this :(
    FASTEST_SUPPORTED_LINK=$(echo "${ETHTOOL_OUTPUT}" | sed -n '/Supported link modes/,/Supported pause frame/p' | sed 's/^[^0-9]*\([0-9]*\).*/\1/' | grep -v "^$" | sort -nu | tail -n1)
    FASTEST_ADVERTISED_LINK=$(echo "${ETHTOOL_OUTPUT}" | sed -n '/Advertised link modes/,/Advertised pause frame/p' | sed 's/^[^0-9]*\([0-9]*\).*/\1/' | grep -v "^$" | sort -nu | tail -n1)
    if [[ -z ${FASTEST_SUPPORTED_LINK} || -z ${FASTEST_ADVERTISED_LINK} ]] ; then
        # Virtual NICs and some drivers do not report link modes
        continue
    fi
    # The fastest possible link ought therefore to be the lowest of supported/advertised
    FASTEST_POSSIBLE_LINK=$(echo -e "${FASTEST_SUPPORTED_LINK}\n${FASTEST_ADVERTISED_LINK}" | sort -n | head -n1)
    CURRENT_LINK=$(echo "${ETHTOOL_OUTPUT}" | grep Speed: | sed 's/^[^0-9]*\([0-9]*\).*/\1/')
    if [[ "${CURRENT_LINK}" != "${FASTEST_POSSIBLE_LINK}" ]] ; then
        echo "The NIC ${NETWORK_DEVICE} is currently running at a speed of ${CURRENT_LINK}, whereas its maximum speed appears to be ${FASTEST_POSSIBLE_LINK}"
        echo "This may indicate a hardware / cabling problem"
        RETURN_CODE=254
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All connected network links running at maximum advertised"
fi

exit ${RETURN_CODE}
