#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that ethernet pause frames (flow control) are disabled"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-662205"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2026-09-10

# Ethernet pause frames (802.3x flow control) stall the whole link when the switch
# or NIC is congested, which causes head-of-line blocking across every process
# sharing that link. WEKA's transport handles packet loss far better than a
# fabric-wide pause, so the recommended configuration is autoneg off, RX off,
# TX off. The Mellanox default (autoneg off, RX on, TX on) is a recurring bad
# configuration in the field.
#
# There is no sysfs interface for pause parameters; the only kernel interface is
# the ETHTOOL_GPAUSEPARAM ioctl, so ethtool -a is the only practical way to read them.

if ! command -v ethtool &> /dev/null ; then
    echo "Unable to locate ethtool; cannot check pause frame settings"
    exit 0
fi

for DEVICE_PATH in /sys/class/net/* ; do
    DEVICE=${DEVICE_PATH##*/}

    # Only ethernet (type 1); pause frames do not apply to e.g. Infiniband (type 32) or loopback
    if [[ ! -e ${DEVICE_PATH}/type ]] || [[ "$(cat ${DEVICE_PATH}/type)" != "1" ]] ; then
        continue
    fi
    # Bonds, VLANs and bridges sit on top of physical ports; the ports themselves are checked directly
    if compgen -G "${DEVICE_PATH}/lower_*" > /dev/null ; then
        continue
    fi
    # Ignore ports with no link (unused/uncabled), as their settings have no effect
    if [[ "$(cat ${DEVICE_PATH}/carrier 2>/dev/null)" != "1" ]] ; then
        continue
    fi

    PAUSE_PARAMS=$(ethtool -a ${DEVICE} 2>/dev/null)
    if [[ -z ${PAUSE_PARAMS} ]] ; then
        # Virtual NICs (veth, tap, etc) do not implement pause parameters
        continue
    fi
    AUTONEG=$(echo "${PAUSE_PARAMS}" | awk '/^Autonegotiate:/{print $2}')
    # Newer ethtool reports the negotiated result separately when autoneg is on; prefer that
    RX_PAUSE=$(echo "${PAUSE_PARAMS}" | awk '/^RX negotiated:/{print $3}')
    TX_PAUSE=$(echo "${PAUSE_PARAMS}" | awk '/^TX negotiated:/{print $3}')
    if [[ -z ${RX_PAUSE} ]] ; then
        RX_PAUSE=$(echo "${PAUSE_PARAMS}" | awk '/^RX:/{print $2}')
    fi
    if [[ -z ${TX_PAUSE} ]] ; then
        TX_PAUSE=$(echo "${PAUSE_PARAMS}" | awk '/^TX:/{print $2}')
    fi

    if [[ "${RX_PAUSE}" == "on" ]] || [[ "${TX_PAUSE}" == "on" ]] ; then
        RETURN_CODE=254
        if [[ "${AUTONEG}" == "off" ]] ; then
            echo "Pause frames are forced on for NIC ${DEVICE}: autoneg=${AUTONEG} rx=${RX_PAUSE} tx=${TX_PAUSE}"
        else
            echo "Pause frames are enabled for NIC ${DEVICE}: autoneg=${AUTONEG} rx=${RX_PAUSE} tx=${TX_PAUSE}"
            echo "Pause autonegotiation is on, so the switch can (re-)enable pause frames on this link"
        fi
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]] ; then
    echo "Pause frames are disabled on all connected ethernet NICs"
else
    echo "Pause frames (802.3x flow control) stall the whole link under congestion and cause head-of-line blocking"
    echo "for every process sharing that link. WEKA handles packet loss better than a paused fabric."
    echo "Please see ${JIRA_REFERENCE} for more information"
    echo "Recommended Resolution: disable pause frames on all NICs and on the corresponding switch ports, e.g."
    echo "  ethtool -A <nic> autoneg off rx off tx off"
    echo "Review your OS documentation for how to set this permanently, e.g. for NetworkManager-based OSes"
    echo "add an ethtool dispatcher script, or for ifcfg-based OSes set ETHTOOL_OPTS=\"-A <nic> autoneg off rx off tx off\""
fi

exit ${RETURN_CODE}
