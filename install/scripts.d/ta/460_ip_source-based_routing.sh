#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Verify if source-based IP routing is required (and set up)"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-360289"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

SOURCE_BASED_ROUTING_RECOMMENDED="0"
NUMBER_OF_ROUTING_TABLES_SEEN="0"
NUMBER_OF_ROUTING_TABLES_VERIFIED="0"
NUMBER_OF_ARP_ANNOUNCE_VERIFIED="0"
NUMBER_OF_ARP_FILTER_VERIFIED="0"

# Look for multiple routes to the same destination via more than one device - this indicates that source-based routing might *possibly* be required because two devices could be on the same subnet
while read -r ROUTING_COUNT ROUTING_DESTINATION ; do
    # If we have more than one route somewhere
    if [[ ${ROUTING_COUNT} -gt "1" ]]; then
        # Now check how many devices route to that destination - more than 1 indicates we probably need to be using SBR
        NUMBER_OF_DEVICES=$(ip -4 --json route | jq -cr '[.[]|select(.dst=="'${ROUTING_DESTINATION}'")]|length')
        if [[ ${NUMBER_OF_DEVICES} -gt "1" ]] ; then
            SOURCE_BASED_ROUTING_RECOMMENDED="1"

            # For each preferred source (i.e. source IP), check that an IP routing rule (directing us to a routing table) exists
            while read -r MAIN_TABLE_ROUTING_DESTINATION MAIN_TABLE_ROUTING_DEVICE MAIN_TABLE_ROUTING_PROTOCOL MAIN_TABLE_ROUTING_SCOPE MAIN_TABLE_ROUTING_SOURCE ; do

                VALID_MATCHING_ROUTE_DESTINATION_IN_TABLE=0
                VALID_MATCHING_ROUTE_DEVICE_IN_TABLE=0

                # For each (hopefully) device-specific routing table, check that they contain routes to the original destination with the correct device, otherwise they won't get used.
                for ROUTING_TABLE in $(ip -4 --json rule | jq -cr '.[]|select(.src=="'${MAIN_TABLE_ROUTING_SOURCE}'")|.table') ; do
                    let NUMBER_OF_ROUTING_TABLES_SEEN="${NUMBER_OF_ROUTING_TABLES_SEEN}+1"

                    while read -r INDIVIDUAL_ROUTE_DESTINATION INDIVIDUAL_ROUTE_DEVICE ; do
                        if [ "${INDIVIDUAL_ROUTE_DESTINATION}" = "${MAIN_TABLE_ROUTING_DESTINATION}" ]  && [ "${INDIVIDUAL_ROUTE_DEVICE}" = "${MAIN_TABLE_ROUTING_DEVICE}" ] ; then
                            let NUMBER_OF_ROUTING_TABLES_VERIFIED="${NUMBER_OF_ROUTING_TABLES_VERIFIED}+1"

                            #Check that arp_announce=2 and arp_filter=1 for this interface, as per docs
                            ARP_ANNOUNCE=$(sysctl -n net.ipv4.conf.${INDIVIDUAL_ROUTE_DEVICE}.arp_announce)
                            ARP_FILTER=$(  sysctl -n net.ipv4.conf.${INDIVIDUAL_ROUTE_DEVICE}.arp_filter)
                            if [[ ${ARP_ANNOUNCE} -eq "2" ]] ; then
                                let NUMBER_OF_ARP_ANNOUNCE_VERIFIED="${NUMBER_OF_ARP_ANNOUNCE_VERIFIED}+1"
                            fi
                            if [[ ${ARP_FILTER} -eq "1" ]] ; then
                                let NUMBER_OF_ARP_FILTER_VERIFIED="${NUMBER_OF_ARP_FILTER_VERIFIED}+1"
                            fi
                        fi
                    done < <(ip -4 --json route list table ${ROUTING_TABLE} | jq -cr ".[]|[(.dst, .dev)] | @tsv")
                done
            done < <(ip -4 --json route | jq -cr '.[]|select(.dst=="'${ROUTING_DESTINATION}'") | [.dst, .dev, .protocol, .scope, .prefsrc] | @tsv') 
        fi
    fi
done < <(ip -4 --json route | jq -cr '.[]|select(.dst!="default")|.dst' | sort | uniq -c) # get all the unique destinations out of the routing table


if [[ ${SOURCE_BASED_ROUTING_RECOMMENDED} -ge "1" ]] ; then
    echo "Multiple routes to a single destination exist - it is possible source-based routing should be configured"

    # Now check we actually do some SBR
    if [[ ${NUMBER_OF_ROUTING_TABLES_SEEN} -eq "0" ]] ; then
        echo "Warning: Although source-based routing is expected, there are no device-specific routing tables configured"
        RETURN_CODE="254"
    fi
    # and for each table...
    if [[ ${NUMBER_OF_ROUTING_TABLES_VERIFIED} -ne ${NUMBER_OF_ROUTING_TABLES_SEEN} ]] ; then
        echo "Warning: Not every device-specific routing table has a route to the relevant destination via the specific interface. The output of \$(ip rule) and \$(ip route) should be reviewed"
        RETURN_CODE="254"
    fi
    if [[ ${NUMBER_OF_ROUTING_TABLES_SEEN} -ne ${NUMBER_OF_ARP_ANNOUNCE_VERIFIED} ]] ; then
        echo "Warning: Not every interface appears to have arp_announce=2 set. This could lead to communication problems"
        RETURN_CODE="254"
    fi
    if [[ ${NUMBER_OF_ROUTING_TABLES_SEEN} -ne ${NUMBER_OF_ARP_FILTER_VERIFIED} ]] ; then
        echo "Warning: Not every interface appears to have arp_filter=1 set. This could lead to communication problems"
        RETURN_CODE="254"
    fi
fi

exit ${RETURN_CODE}
