#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that the setting rp_filter is set to either 0 or 2"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE="SFDC 12492"
RETURN_CODE=0

# https://sysctl-explorer.net/net/ipv4/rp_filter/
# 0 - No source validation.
# 1 - Strict mode as defined in RFC3704 Strict Reverse Path Each incoming packet is tested against the FIB and if the interface is not the best reverse path the packet check will fail. By default failed packets are discarded.
# 2 - Loose mode as defined in RFC3704 Loose Reverse Path Each incoming packet’s source address is also tested against the FIB and if the source address is not reachable via any interface the packet check will fail.

# Current recommended practice in RFC3704 is to enable strict mode to prevent IP spoofing from DDos attacks. If using asymmetric routing or other complicated routing, then loose mode is recommended.

# The max value from conf/{all,interface}/rp_filter is used when doing source validation on the {interface}. <-- IMPORTANT!

# Default value is 0. Note that some distributions enable it in startup scripts.

# Nb: per interface setting (where “interface” is the name of your network interface); “all” is a special interface: changes the settings for all interfaces.

RP_FILTER_VALUE_ALL=$(sysctl -n net.ipv4.conf.all.rp_filter)

# If rp_filter is set to 2, on the "all" interface,
# no further checks are necessary
if [[ $RP_FILTER_VALUE_ALL != "2" ]]; then
  interfaces=($(ip -4 -o addr | awk '{print $2}' | uniq | grep -vw "lo"))
  for INTERFACE in "${interfaces[@]}"; do
    RP_FILTER_VALUE=$(sysctl -n net.ipv4.conf.${INTERFACE}.rp_filter)
    if [[ $RP_FILTER_VALUE == "1" ]]; then
      RETURN_CODE="254"
      echo "The value for net.ipv4.conf.${INTERFACE}.rp_filter is set to ${RP_FILTER_VALUE}."
      echo "This can disrupt floating IP addresses for protocols."
      echo "It is recommended to set net.ipv4.conf.${INTERFACE}.rp_filter to 2."
      echo "Recommended resolution: set this value in e.g. /etc/sysctl.d/99-weka-nics.conf"
    elif [[ $RP_FILTER_VALUE_ALL == "1" && $RP_FILTER_VALUE == "0" ]]; then
      RETURN_CODE="254"
      echo "The value for net.ipv4.conf.${INTERFACE}.rp_filter is set to ${RP_FILTER_VALUE}."
      echo "The value for net.ipv4.conf.all.rp_filter is set to ${RP_FILTER_VALUE_ALL} and takes precedence."
      echo "This can disrupt floating IP addresses for protocols."
      echo "It is recommended to set net.ipv4.conf.${INTERFACE}.rp_filter or net.ipv4.conf.all.rp_filter to 2."
      echo "Recommended resolution: set this value in e.g. /etc/sysctl.d/99-weka-nics.conf"
    fi
  done
else
  echo "net.ipv4.conf.all.rp_filter is set to 2, no further testing necessary."
fi

exit ${RETURN_CODE}
