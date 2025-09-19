#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for network mode and port consistency"
SCRIPT_TYPE="single"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
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

for ROLE in COMPUTE DRIVES FRONTEND; do
    if [[ $(weka cluster process -F role="${ROLE}" -o netmode --no-header | sort | uniq | wc -l) -gt 1 ]]; then
        RETURN_CODE=254
        echo "WARNING: "${ROLE}" process network modes are inconsistent"
        echo "Recommended Resolution: contact Customer Success to ensure that each container is defined correctly"
    fi

    # Sample output (weka cluster process):
    #  121  10.0.94.115, 10.0.98.115  DPDK / GDS
    #  122  10.0.94.115, 10.0.98.115  DPDK / GDS
    while IFS= read -r line; do
        # Extract the first field (ID)
        ID="${line%% *}"

        # Remove the ID from the line
        rest="${line#* }"

        # Extract the IPs part (up to the first non-IP word)
        ip_section=$(echo "$rest" | grep -oE '([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(,[[:space:]]*)?)+')

        # Clean up IP section: remove spaces
        clean_ips=$(echo "$ip_section" | tr -d ' ')

        # Convert IPs into Bash array
        IFS=',' read -r -a IPS <<< "$clean_ips"

        # Extract the suffix (after the IPs)
        suffix="${rest#"$ip_section"}"
        suffix=$(echo "$suffix" | xargs)  # Trim whitespace

        # Determine protocol
        if [[ "$suffix" == *DPDK* ]]; then
            NETMODE="DPDK"
        elif [[ "$suffix" == *UDP* ]]; then
            NETMODE="UDP"
        else
            NETMODE="OTHER"
        fi

        # Sample output (weka debug net ports):
        #  PCI           NAME       DRIVER     IP ADDRESS   NETMASK  GATEWAY  MTU   VLAN  LINK SPEED (MBPS)  LINK UP  LOCAL L2ADDR       BACKEND
        #  0000:3b:00.0  ens1f0np0  mlx5_pci   10.0.98.114  16       0.0.0.0  1518  0     100000             True     98:03:9b:9d:79:30  DPDK
        #  0000:3b:00.0  ens1f0np0  mlx5_core  10.0.98.114  16       0.0.0.0  4014  0     0                  True     98:03:9b:9d:79:30  UDP
        #  0000:3b:00.1  ens1f1np1  mlx5_pci   10.0.94.114  16       0.0.0.0  1518  0     100000             True     98:03:9b:9d:79:31  DPDK
        #  0000:3b:00.1  ens1f1np1  mlx5_core  10.0.94.114  16       0.0.0.0  4014  0     0                  True     98:03:9b:9d:79:31  UDP
        for IP in ${IPS[@]}; do
            if [[ -z "$(weka debug net ports "${ID}" -F ip="${IP}" -F backendType="${NETMODE}")" ]]; then
                echo "WARN: Process "${ID}" ("${ROLE}") has no port registered for IP "${IP}" and network mode "${NETMODE}""
                echo "Run the following command for details: weka debug net ports ${ID}"
                RETURN_CODE=254
            fi
        done
    done < <(weka cluster process -b -F role="${ROLE}" -o id,ips,netmode --no-header)
done

if [[ $RETURN_CODE -eq 0 ]]; then
    echo "Backend process network modes are consistent."
fi

exit $RETURN_CODE