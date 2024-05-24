#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check source-based routing for NFS aliases"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2024-04-24

# Known limitations:
# - Assumes the ganesha container is associated with a container named frontend0
# - Will not validate the source-based routing rules are correct, only that they exist
# - Requires that the weka binary be available and the account logged onto the cluster

main() {
   # Check if we can run weka commands
   weka status &> /dev/null
   if [[ $? -ne 0 ]]; then
     echo "ERROR: Not able to run weka commands"
     exit 254
   elif [[ $? -eq 127 ]]; then
     echo "WEKA not found"
     exit 254
   elif [[ $? -eq 41 ]]; then
     echo "Unable to login into Weka cluster."
     exit 254
   fi

   # Obtain current host id
   # Filtering on container="frontend0" may not be the best approach...
   weka_host_id=$(weka cluster container -o id --no-header -F hostname="$(hostname)" -F container="frontend0")
   #weka_host_id=$(weka cluster container -o id --no-header -F hostname="$(hostname)")

   # Iterate over NFS alias assignments, for this host
   # Sample output, from weka nfs interface-group assignment:
   #  172.31.80.77  HostId: 14  eth0  nfs-ig1
   #  172.31.80.78  HostId: 14  eth0  nfs-ig1

   overlapping_subnets=0
   while read NFS_IP; do
     local interfaces=($(ip -4 -o addr | awk '{print $2}' | uniq))
     for interface in "${interfaces[@]}"; do
       if ip_in_interface_subnet "$NFS_IP" "$interface"; then
         #echo "IP $NFS_IP belongs to subnet on interface $interface"
         overlapping_subnets=$((overlapping_subnets+1))
       fi
     done
   done < <(weka nfs interface-group assignment --no-header | awk '$3 == '$weka_host_id'' | awk '{print $1}')

   # There is more than 1 subnet that overlaps with the NFS alias range.
   # Ostensibly, this would indicate source based routing needs to be configured.
   if [[ $overlapping_subnets -gt 1 ]]; then
     while read NFS_IP; do
       found_rule=0
       while read IP_RULE_SUBNET; do
         if ip_in_subnet "$NFS_IP" "$IP_RULE_SUBNET"; then
           echo "INFO: Found IP/subnet $IP_RULE_SUBNET in ip rule for address $NFS_IP"
           found_rule=1
           continue
         fi
       done < <(ip -4 rule | awk '{print $3}' | grep -v "all")
       if [[ $found_rule -eq 0 ]]; then 
         echo "WARNING: No ip rule for address $NFS_IP! It is possible source-based routing should be configured."
         RETURN_CODE=254		 
       fi
     done < <(weka nfs interface-group assignment --no-header | awk '$3 == '$weka_host_id'' | awk '{print $1}')

     exit $RETURN_CODE

   # No overlapping subnets -- exit w/ success
   else
     exit $RETURN_CODE
   fi
}

ip_in_interface_subnet() {
   local ip="$1"
   local interface="$2"

   #echo "Checking interface $interface for overlap with $ip..."
   local subnet=$(ip -o -f inet addr show "$interface" | grep -v secondary |  awk '{print $4}')
   if [ -n "$subnet" ]; then
     if ip_in_subnet "$ip" "$subnet"; then
       return 0 
     fi
   fi
   return 1
}

ip_to_decimal() {
    local ip="$1"
    local decimal=""
    local octets=($(echo "$ip" | tr '.' ' '))
    for octet in "${octets[@]}"; do
      decimal=$((decimal * 256 + octet))
    done
    echo "$decimal"
}

# Function to determine if IP address belongs to a subnet
ip_in_subnet() {
    local ip="$1"
    local subnet="$2"

    # Extract subnet and subnet mask
    if [[ "$subnet" =~ .*\/ ]]; then
      local subnet_ip=$(echo "$subnet" | cut -d '/' -f 1)
      local subnet_mask=$(echo "$subnet" | cut -d '/' -f 2)
    else
      local subnet_ip=$subnet
      local subnet_mask="32"
    fi

    # Convert IP address and subnet IP address to decimal
    local ip_decimal=$(ip_to_decimal "$ip")
    local subnet_ip_decimal=$(ip_to_decimal "$subnet_ip")

    # Calculate the subnet mask in decimal
    local bitmask=$((0xFFFFFFFF << (32 - subnet_mask)))
	
    # Calculate the network address
    local network_address=$((subnet_ip_decimal & bitmask))

    # Calculate the IP address in the same subnet
    local ip_in_subnet_decimal=$((ip_decimal & bitmask))

    if [ "$network_address" == "$ip_in_subnet_decimal" ]; then
      return 0;
    else
      return 1;
    fi
}

main "$@"
