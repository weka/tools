#!/bin/bash

usage() {
    echo "Usage: $(basename "$0") V1.0 [options]"
    echo "Scripts requires weka version >= 4.3.3"
    echo "Options:"
	echo "  -s, --servers SRV1,SRV2   Specify all SMBW servers"
	echo "  -h, --help                Show this help message and exit"
    exit 0
}

hosts=()

send_command_to_host() {
    local cmd="$1"
    local host="$2"
    ssh $host $cmd
}

issue_event() {
    local msg="$1"
    send_command_to_host "weka events trigger-event \"$msg\"" ${hosts[0]}
}

# Parse command-line options
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        -s|--servers)
            IFS=',' read -ra hosts <<< "$2"
            shift 1
            echo "${hosts[@]}"
            ;;
        *)
            echo "Error: Unknown option: $1"
            usage
            ;;
    esac
    shift
done

# Main
# Generate password
pcs_pass=$(< /dev/urandom tr -dc 'A-Za-z0-9' | head -c16)

# Update stored password
weka debug config assign sambaClusterInfo pcsPass=$pcs_pass

# Change the local password on each smbw container
for host in "${hosts[@]}"; do
	send_command_to_host "weka local restart smbw --dont-restart-dependent-containers" "$host"
done
wait

# Re-login to each pcs cluster
for host in "${hosts[@]}"; do
	send_command_to_host "weka local exec --container smbw -- pcs cluster auth ${hosts[@]} -u hacluster -p ${pcs_pass}" "$host"
done
wait

issue_event "SMBW cluster is now using a new random generated password"

echo "Wer'e Done, please let SMBW server a few minutes to go back on-line"

