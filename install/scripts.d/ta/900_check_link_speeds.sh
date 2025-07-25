#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check ethernet link speeds are at maximum advertised"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
REFERENCE="WEKAPP-482528"

RETURN_CODE=0

# We can't rely on jq :(
for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header | grep -e drive -e compute -e frontend); do
    for NETWORK_DEVICE in $(weka local resources net --container ${WEKA_CONTAINER} --json --stable | grep name | awk '{print $2}' | sed 's/[^0-9a-zA-Z]//g'); do
        # need to find the fastest shared link speed between "supported" and "advertised" links.
        # there's no /sys/class/net interface to this, and the only kernel interface is ethtool-netlink, as far as I can find:
        #   https://www.kernel.org/doc/html/v5.9/networking/ethtool-netlink.html#linkmodes-get
        # ethtool only recently (v6.11) started supporting json output, so I can't find any other way of doing this :(
        FASTEST_SUPPORTED_LINK=$(ethtool ${NETWORK_DEVICE} | sed -n '/Supported link modes/,/Supported pause frame/p' | sed 's/^[^0-9]*\([0-9]*\).*/\1/' | grep -v "^$" | sort -nu | tail -n1)
        FASTEST_ADVERTISED_LINK=$(ethtool ${NETWORK_DEVICE} | sed -n '/Advertised link modes/,/Advertised pause frame/p' | sed 's/^[^0-9]*\([0-9]*\).*/\1/' | grep -v "^$" | sort -nu | tail -n1)
        # The fastest possible link ought therefore to be the lowest of supported/advertised
        FASTEST_POSSIBLE_LINK=$(echo -e "${FASTEST_SUPPORTED_LINK}\n${FASTEST_ADVERTISED_LINK}" | sort -n | head -n1)
        CURRENT_LINK=$(ethtool ${NETWORK_DEVICE} | grep Speed: | sed 's/^[^0-9]*\([0-9]*\).*/\1/')
        if [[ "${CURRENT_LINK}" != "${FASTEST_POSSIBLE_LINK}" ]] ; then
            echo "The NIC ${NETWORK_DEVICE} is currently running at a speed of ${CURRENT_LINK}, whereas its maximum speed appears to be ${FASTEST_POSSIBLE_LINK}"
            echo "This may indicate a hardware / cabling problem"
            RETURN_CODE=254
        fi
        
    done
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All network links running at maximum advertised"
fi

exit ${RETURN_CODE}
