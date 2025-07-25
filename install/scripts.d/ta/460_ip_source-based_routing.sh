#!/bin/bash 

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Verify if source-based IP routing is required (and set up)"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-360289"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

declare -A WEKA_INTERFACES
declare -A WEKA_INTERFACES_OVERLAP

# Last modified: 2025-03-25

# arp_announce -- Weka recommends a value of 2
#  Ref: https://sysctl-explorer.net/net/ipv4/arp_announce/
#   Define different restriction levels for announcing the local source IP address from IP packets in ARP requests sent on interface: 
#   0 - (default) Use any local address, configured on any interface 
#   1 - Try to avoid local addresses that are not in the target’s subnet for this interface. 
#       This mode is useful when target hosts reachable via this interface require the source IP address in ARP requests to be part of their logical network configured on the receiving interface. 
#       When we generate the request we will check all our subnets that include the target IP and will preserve the source address if it is from such subnet. 
#       If there is no such subnet we select source address according to the rules for level 2. 
#   2 - Always use the best local address for this target. In this mode we ignore the source address in the IP packet and try to select local address that we prefer for talks with the target host. 
#       Such local address is selected by looking for primary IP addresses on all our subnets on the outgoing interface that include the target IP address. 
#       If no suitable local address is found we select the first local address we have on the outgoing interface or on all other interfaces, with the hope we will receive reply for our request and even sometimes no matter the source IPaddress we announce.
#
#       The max value from conf/{all,interface}/arp_announce is used.

# arp_filter -- Weka recommends a value of 1
#  Ref: https://sysctl-explorer.net/net/ipv4/arp_filter/
#   1 - Allows you to have multiple network interfaces on the same subnet, and have the ARPs for each interface be answered based on whether or not the kernel would route a packet from the ARP’d IP out that interface (therefore you must use source based routing for this to work). 
#       In other words it allows control of which cards (usually 1) will respond to an arp request.
#   0 - (default) The kernel can respond to arp requests with addresses from other interfaces. 
#       This may seem wrong but it usually makes sense, because it increases the chance of successful communication. 
#       IP addresses are owned by the complete host on Linux, not by particular interfaces. 
#       Only for more complex setups like load- balancing, does this behaviour cause problems.
#
#       arp_filter for the interface will be enabled if at least one of conf/{all,interface}/arp_filter is set to TRUE, it will be disabled otherwise

# arp_ignore -- Weka recommends a value of 0
#  Ref: https://sysctl-explorer.net/net/ipv4/arp_ignore/
#   Define different modes for sending replies in response to received ARP requests that resolve local target IP addresses: 
#   0 - (default): reply for any local target IP address, configured on any interface 
#   1 - reply only if the target IP address is local address configured on the incoming interface 
#   2 - reply only if the target IP address is local address configured on the incoming interface and both with the sender’s IP address are part from same subnet on this interface 
#   3 - do not reply for local addresses configured with scope host, only resolutions for global and link addresses are replied 
#   4-7 - reserved 
#   8 - do not reply for all local addresses
#
#   The max value from conf/{all,interface}/arp_ignore is used when ARP request is received on the {interface


get_network_prefix() {
    local cidr="$1"

    if [[ "$cidr" == *:* ]]; then
        # IPv6 Handling (manual, Bash-only)
        local ip="${cidr%/*}"
        local prefix_len="${cidr#*/}"
        local -a blocks

        # Expand abbreviated IPv6 address (::, etc.)
        IFS=':' read -ra parts <<< "$ip"
        local num_parts=${#parts[@]}

        local fill=$(( 8 - num_parts + 1 ))
        for ((i=0; i<num_parts; i++)); do
            if [[ -z "${parts[i]}" ]]; then
                # "::" detected — expand zeros
                for ((j=0; j<fill; j++)); do
                    blocks+=("0000")
                done
            else
                blocks+=("$(printf '%04x' 0x${parts[i]})")
            fi
        done

        # Fill to 8 hextets if needed
        while [ "${#blocks[@]}" -lt 8 ]; do
            blocks+=("0000")
        done

        # Determine how many full hextets belong to the network prefix
        local full_blocks=$(( prefix_len / 16 ))
        local partial_bits=$(( prefix_len % 16 ))

        for ((i=0; i<8; i++)); do
            if (( i < full_blocks )); then
                continue
            elif (( i == full_blocks && partial_bits > 0 )); then
                local val=$(( 0x${blocks[i]} ))
                local mask=$(( 0xFFFF << (16 - partial_bits) & 0xFFFF ))
                blocks[i]=$(printf '%04x' $(( val & mask )))
            else
                blocks[i]="0000"
            fi
        done

        # Reconstruct IPv6 prefix (remove leading zeros and compress if needed)
        local prefix=$(IFS=:; echo "${blocks[*]}")
        echo "$prefix"
    else
        # IPv4 Handling
        local ip subnet mask IFS=.
        ip="${cidr%/*}"
        subnet="${cidr#*/}"
        mask=$(( (1 << subnet) - 1 << (32 - subnet) ))
        set -- $ip
        local -a octets=($1 $2 $3 $4)
        local ip_int=$(( (${octets[0]} << 24) | (${octets[1]} << 16) | (${octets[2]} << 8) | ${octets[3]} ))
        local net_int=$(( ip_int & mask ))
        local net_addr=$(( (net_int >> 24) & 255 )).$(( (net_int >> 16) & 255 )).$(( (net_int >> 8) & 255 )).$(( net_int & 255 ))
        echo "$net_addr"
    fi
}



# Checks: 
#  IP rule exists for each mgmt ip
#  IP route table exists for each IP rule above

#  Verify arp_announce
#  Verify arp_filter
#  Verify arp_ignore

	
# Determine what NICs are being used as dataplane NICs
for WEKA_CONTAINER in $(weka local ps --output name --no-header | grep -e compute -e drive -e frontend); do
    while read NET_ENTRY; do
        if [[ ${NET_ENTRY} =~ "name:"(.*) ]]; then
            NET_NAME=${BASH_REMATCH[1]}
            # Example output:
            #  [{addr_info:[{index:8,dev:ens1f1np1,family:inet,local:10.0.94.110,prefixlen:16,broadcast:10.0.255.255,scope:global,noprefixroute:true,label:ens1f1np1,valid_life_time:4294967295,preferred_life_time:4294967295}]}]
            if [[ $(ip -4 -j -o addr show dev ${NET_NAME} 2>/dev/null | tr -d \"\[:blank:]) =~ "local:"([0-9\.]+)",prefixlen:"([0-9]+) ]]; then
                NET_IP=${BASH_REMATCH[1]}
                NETMASK=${BASH_REMATCH[2]}
                WEKA_INTERFACES[${NET_NAME}]="${NET_IP}/${NETMASK}"
            fi
        fi
    done < <(weka local resources -C ${WEKA_CONTAINER} net --stable -J | grep -w -e name | tr -d \"\,[:blank:])
done


# Determine the network prefix associated with each dataplane NIC
if [[ ${#WEKA_INTERFACES[@]} -gt 1 ]]; then
    declare -A network_prefixes
    
    # Do the dataplane NICs have addresses in overlapping networks?
    for NET in "${!WEKA_INTERFACES[@]}"; do
        network_prefix=$(get_network_prefix "${WEKA_INTERFACES[$NET]}")
        WEKA_INTERFACES_OVERLAP[${network_prefix}]+="${NET} "
    done
fi


# If we have multiple, overlapping, dataplane NICs, perform validation
for PREFIX in ${!WEKA_INTERFACES_OVERLAP[@]}; do
    readarray -d ' ' overlapping_nics  <<< "${WEKA_INTERFACES_OVERLAP[${PREFIX}]}"
    if [[ ${#overlapping_nics[@]} -gt 1 ]]; then
        for NIC in ${overlapping_nics[@]}; do
        
            # Validate arp_announce (should be equal to 2)
            ARP_ANNOUNCE_ALL=$(sysctl -n net.ipv4.conf.all.arp_announce)
            if [[ ${ARP_ANNOUNCE_ALL} != "2" ]]; then
                if [[ $(sysctl -n net.ipv4.conf.${NIC}.arp_announce) != "2" ]]; then
                    RETURN_CODE=254
                    echo "WARNING: arp_announce is not set to 2 on interface ${NIC}".
                fi
            fi
    
            # Validate arp_filter (should be equal to 1)
            ARP_FILTER_ALL=$(sysctl -n net.ipv4.conf.all.arp_filter)
            if [[ ${ARP_FILTER_ALL} != "1" ]]; then
                if [[ $(sysctl -n net.ipv4.conf.${NIC}.arp_filter) != "1" ]]; then
                    RETURN_CODE=254
                    echo "WARNING: arp_filter is not set to 1 on interface ${NIC}".
               fi
            fi
    
            # Validate arp_ignore (should be 0)
            if [[ $(sysctl -n net.ipv4.conf.${NIC}.arp_ignore) != "0" ]]; then
                RETURN_CODE=254
                echo "WARNING: arp_ignore is not set to 0 on interface ${NIC}".
            fi
        
            if [[ $(sysctl -n net.ipv4.conf.all.arp_ignore) != "0" ]]; then
                RETURN_CODE=254
                echo "WARNING: arp_ignore is not set to 0 on net.ipv4.conf.all.arp_ignore."
                echo "This value may override the arp_ignore value on specific network interfaces."
            fi
        
            ###################################
            # Check ip rules / routing tables #
            ###################################
            readarray -d "/" -t netinfo  <<< "${WEKA_INTERFACES[${NIC}]}"
        
            # Does this interface's IP appear in the rule table?
            if ! ip rule | grep -q -m 1 -F "${netinfo[0]}"; then
                RETURN_CODE=254
                echo "WARNING: No ip rule found for IP ${netinfo[0]}".
            else
                ROUTE_TABLE=$(ip rule | grep -m 1 -F "${netinfo[0]}" | sed -r 's/.*lookup *(\w+).*/\1/')
                if ! ip route show table ${ROUTE_TABLE} &> /dev/null; then
                    RETURN_CODE=254
                    echo "WARNING: route table ${ROUTE_TABLE} not found."
               fi
            fi
        done 
    fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Source-based routing is not required or is correct."
else
    echo "Recommended Resolution: review the required network settings from the WEKA docs:"
    echo "https://docs.weka.io/planning-and-installation/bare-metal/setting-up-the-hosts#general-settings-in-etc-sysctl.conf"
fi
exit ${RETURN_CODE}
