#!/bin/bash
#Safely serially reboot all hosts present in provided hosts file. See configuration section for options
#Waits for S3 to drain then reboots host; logs results to file for review
#Requires passwordless ssh with sudo priviledges

##### Configuration #####
HOST_LIST=./hosts           #File containing hostnames to reboot - 1 per line. Allows skipping hosts by prepending a line with #
DRIVE_FAILURE_MAX=0         #Number of failed drives to tolerate, otherwise reboot the host again
MIN_UPTIME=0                #Minutes - Skip recently rebooted hosts
S3_DRAIN_TIME=90            #Seconds - Minimum time to wait for S3 to finish draining before rebooting anyway
COMMENT_COMPLETED=true      #Comment out host in HOST_LIST file once complete to allow continuing interupted runs
CHECK_INTERVAL=30           #Seconds between drive/ssh/weka status checks
CHECK_COUNT_LIMIT=5         #Number of times to check drives before rebooting again if more drives down than specified by DRIVE_FAILURE_MAX
DRY_RUN=false               #If true: don't actually drain S3 and reboot.
SKIP_IF_OFFLINE=true        #Allow skipping hosts that are offline before we have interacted with them
LOG_DRIVE_IDS=true          #Log Failed drive IDs to the log file and console
TRY_PCIE_RESCAN=true        #Try rescanning PCIe bus before restarting on failed drives. ***Use only on NVMe drives***
SKIP_ON_S3_DRAIN_FAIL=false #If S3 fails to drain then skip host instead of rebooting

SSH_USER="$(whoami)"        #Specify remote username
LOG_FILE="$(basename "$0" | sed 's/\.[^.]*$//')_$(date '+%Y%m%d_%H%M%S').log"

##### END CONFIGURATION #####

trap clean_exit INT TERM #Catch CTRL+C and exit cleanly
set -euo pipefail        #Exit on errors & unset variable use

log() {
	local message="$1"
	local timestamp
	timestamp=$(date '+%Y-%m-%d %H:%M:%S')
	echo "$message"
	echo "$timestamp: $message" >> "$LOG_FILE"
}

if [ ! -e "$HOST_LIST" ]; then log "ERROR: Hosts list $HOST_LIST does not exist."; exit 1; fi

clean_exit() {
	log "ABORT:      Script interrupted. Exiting."
	exit 2
}

wait_for_ssh() {
	local host="$1"
	log "WAITING:    for $host to be reachable over ssh"
	sleep "$CHECK_INTERVAL"

	while true; do
	# Attempt to connect via SSH and run a weka command
		if ssh -l "$SSH_USER" -o ConnectTimeout=5 -o BatchMode=yes "$host" "weka status" >/dev/null 2>&1; then
			log "CONTINUING: $host is online."
			return 0
		else
			log "WAITING:    $host is still offline"
			sleep $CHECK_INTERVAL
		fi
	done
}

wait_for_weka_ok() {
	#Loop indefinitely as we must not continue if WEKA status is not OK, this can take hours depending on rebuilds
	local host="$1"
	log "WAITING:    WEKA Cluster is not Status: OK"
	while true; do
		local status_output
		status_output=$(ssh -l "$SSH_USER" "$host" 'weka status' 2>/dev/null)
		local status_line
		status_line=$(echo "$status_output" | grep -m 1 '^ *status: ' | sed 's/^ *s/S/' || echo "Status: Unknown")
		if echo "$status_line" | grep -q 'Status: OK'; then
			log "CONTINUING: $status_line"
			return 0  # Exit the function if status is OK
		else
			log "WAITING:    $status_line"
			sleep $CHECK_INTERVAL
		fi
	done
}

pcie_rescan() {
	local host=$1
	local drive_info=$2
	local new_info=$3
	local failed
	#Get current failed drives for host
	failed=$(echo "$new_info" | grep -vwe ACTIVE -e PHASING_IN -e HOSTNAME || true)
	echo "$failed" | while IFS= read -r drive; do
		local uid
		uid=$(echo "$drive" | awk '{print $2}') #parse $drive down to just uid
		log "DRIVE:      Processing failed drive with UID: $uid"

		local pci_data
		pci_data=$(echo "$drive_info" | awk -v uid="$uid" '$2 == uid {print $0}')
		if [ -n "$pci_data" ]; then
			local drive_host
			drive_host=$(echo "$pci_data" | awk '{print $4}')
			local pci_id
			pci_id=$(echo "$pci_data" | awk '{print $3}')

			if [ "$drive_host" == "$host" ]; then
				log "DRIVE:      Host safety check passed; Removing drive $uid"
				#Check if failed drive ID is on the PCIe bus: ls /sys/bus/pci/devices/<id>
				#If on the bus, remove: echo "1" > /sys/bus/pci/devices/<id>/remove
				local ssh_output
				ssh_output=$(ssh -l "$SSH_USER" -n "$host" "[ -d /sys/bus/pci/devices/$pci_id ] && echo 'present' || echo 'absent'")

				if [ "$ssh_output" == "present" ]; then
					log "DRIVE:      $uid is present in the PCIe bus. Removing it now."
					ssh -l "$SSH_USER" -n "$host" "echo '1' | sudo tee /sys/bus/pci/devices/$pci_id/remove > /dev/null"
				else
					log "DRIVE:      $uid is not present in the PCIe bus, a reboot may be required."
				fi
			else
				log "DRIVE:      Host mismatch for UID: $uid. Expected: $host, Found: $drive_host"
				log "FATAL:      Drive host mismatched, exiting!"
				echo -e "\a" #Ring the bell on fatal error
				exit 3
			fi
		else
			log "DRIVE:      UID $uid is failed; It was not present before rebooting."
		fi
	done
	log "DRIVE:      Rescanning PCI bus"
	ssh -l "$SSH_USER" "$host" "echo '1' | sudo tee /sys/bus/pci/rescan > /dev/null"
}

wait_for_drain() {
	local host=$1
	local version=$2
	local start_time
	local end_time
	start_time=$(date +%s)
	end_time=$((start_time + S3_DRAIN_TIME))
	local connections
	while [ "$(date +%s)" -lt $end_time ];do
		sleep $CHECK_INTERVAL
		if echo "$version" | grep "^4\.[0-3]\." > /dev/null;then
			connections=$(ssh -l "$SSH_USER" "$host" "curl -s http://localhost:9001/minio/reqswatermark/currentreqs | grep -o '[0-9]*'") #Pre-4.4
			else
			connections=$(ssh -l "$SSH_USER" "$host" 'weka s3 cluster status -o requests -F hostname=$(hostname) --no-header') #4.4+
		fi
		if [ "$connections" = 0 ]; then
			log "INFO:       S3 finished draining on $host"
			return 0
		fi
	done
	log "ERROR:     S3 Failed to drain in time on $host"
	return 1
}

reboot_host() {
	local host=$1
    ssh -l "$SSH_USER" -o ServerAliveInterval=1 -o ServerAliveCountMax=5 "$host" "
	(sleep 1 && sudo shutdown -r now &>/dev/null &) &
	exit 0" &>/dev/null || true
}

#Main Script
rebooted=0
skipped=0
failed_drives=0
mapfile -t HOSTS < "$HOST_LIST"
for host in "${HOSTS[@]}"; do
	log ""
	log "INFO:      Processing $host"
	#Skip if we're running on the local machine
	local_hostname=$(hostname)
	if [[ "${host%%.*}" == "${local_hostname%%.*}" ]]; then log "SKIPPING:   $host due to it being localhost"; skipped=$((skipped + 1)); continue; fi
	#Skip if commented out
	if [[ $host == \#* ]]; then log "SKIPPING:   $host due to leading #"; skipped=$((skipped + 1)); continue; fi
	if ! ssh -l "$SSH_USER" -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$host" "exit" 2>/dev/null;then
		log "ERROR:      $host is offline"
		if [ "$SKIP_IF_OFFLINE" != true ];then
			log "FATAL:      Host is offline, set SKIP_IF_OFFLINE in the configuration section to allow continuing in this case"
			echo -e "\a" #Ring the bell on fatal error
			exit 1;
		else
			log "SKIPPING:   Host is offline, SKIPPING"
			skipped=$((skipped + 1))
			continue
		fi
	fi
	#Check uptime
	uptime_minutes=$(ssh -l "$SSH_USER" "$host" "awk '{print int(\$1/60)}' /proc/uptime")
	if [ "$uptime_minutes" -lt "$MIN_UPTIME" ]; then
		log "SKIPPING:   $host due to host uptime being less than $MIN_UPTIME minutes."
		skipped=$((skipped + 1))
		continue
	fi
	#Get current drive count
	version=$(ssh -l "$SSH_USER" "$host" "weka version current")
	drive_count=$(ssh -l "$SSH_USER" "$host" 'weka cluster drive -F hostname=$(hostname),status=ACTIVE --no-header | wc -l' 2>/dev/null)
	status=wait_for_ok
	#Start loop
	#Check WEKA Status
	wait_for_weka_ok "$host"
	while [ "$status" != "good" ]; do
		#Save drive locations
		drive_info=$(ssh -l "$SSH_USER" "$host" 'weka cluster drive -F hostname=$(hostname) -o id,uid,path,hostname,status,serial')
		#Drain S3 & reboot
		if [ "$DRY_RUN" = false ];then
			s3_running=$(ssh -l "$SSH_USER" "$host" 'if weka local status s3 &>/dev/null;then echo true;else echo false;fi')
			if [ "$s3_running" = true ];then
				log "---LIVE---: Draining S3 of $host"
				if echo "$version" | grep "^4\.[0-3]\." > /dev/null;then #Pre-4.4
					ssh -l "$SSH_USER" "$host" 'weka s3 cluster drain $(weka cluster container -F hostname=$(hostname) -o id,container --no-header | awk "/frontend/ {print \$1}")'
				else #4.4+
					ssh -l "$SSH_USER" "$host" 'weka s3 cluster drain $(weka s3 cluster status -F hostname=$(hostname) -o id --no-header)'
				fi
				if wait_for_drain "$host" "$version";then
					log "---LIVE---: Host $host drained; rebooting"
					reboot_host "$host"
					rebooted=$((rebooted + 1))
				else
					if [ "$SKIP_ON_S3_DRAIN_FAIL" = false ];then
						log "ERROR:      Host $host failed to drain; rebooting anyway"
						reboot_host "$host"
						rebooted=$((rebooted + 1))
					else
					log "ERROR:      Failed to drain S3 on $host, SKIPPING."
					skipped=$((skipped + 1))
					fi
				fi
			else
				log "---LIVE---: No S3 running; rebooting $host"
				reboot_host "$host"
				rebooted=$((rebooted + 1))
			fi
		else
			log "DRY RUN:    Drain and reboot $host here"
			ssh -l "$SSH_USER" "$host" "echo \$(hostname) Frontend ID: \$(weka cluster container -F hostname=\$(hostname) -o id,container --no-header | awk '/frontend/ {print \$1}')"
		fi
		#Wait for reboot
		wait_for_ssh "$host"
		#Check drive count
		status=checking_drives
		sleep 3
		for ((j = 0; j < CHECK_COUNT_LIMIT; j++)); do
			for ((i = 0; i < CHECK_COUNT_LIMIT; i++)); do
				new_drive_info=$(ssh -l "$SSH_USER" "$host" 'weka cluster drive -F hostname=$(hostname) -o id,uid,path,hostname,status,serial')
				new_drives_count=$(echo "$new_drive_info" | grep -cwe "ACTIVE" -e "PHASING_IN" || true 2>/dev/null)
				drive_failures=$((drive_count - new_drives_count))
				if [ "$drive_failures" -gt "$DRIVE_FAILURE_MAX" ]; then
					log "DRIVE:      $host has exceeded drive failure limit: $drive_failures failures"
					status=failed_drive_limit_exceeded
					sleep $CHECK_INTERVAL
				elif [ "$drive_failures" = 0 ]; then
					log "CONTINUING: $host has no drive failures"
					failed_drives=$((failed_drives + drive_failures))
					status=good
					break 2
				else
					log "WAITING:    $host has $drive_failures failures; Within acceptable range (no further reboots)"
					failed_drives=$((failed_drives + drive_failures))
					status=good
				fi
			done
			if [ "$LOG_DRIVE_IDS" = true ] && [ "$drive_failures" -gt 0 ];then
				log "INFO:       Failed Drive IDs (Pre-rescan):
$(echo "$new_drive_info" | grep -vwe ACTIVE -e PHASING_IN)"
			fi
			#Do PCIe Rescan
			if [ "$TRY_PCIE_RESCAN" = true ];then
				pcie_rescan "$host" "$drive_info" "$new_drive_info"
			else
				break
			fi
		done
	done
	if [ "$LOG_DRIVE_IDS" = true ] && [ "$drive_failures" -gt 0 ];then
		log "INFO:       Failed Drive IDs (Post-rescan):
$(echo "$new_drive_info" | grep -vwe ACTIVE -e PHASING_IN)"
	fi
	#Comment out host in file
	if [ "$COMMENT_COMPLETED" = true ]; then
		log "INFO:       Commenting out completed host"
		sed -i "s/^${host}$/#${host}/" "$HOST_LIST"
	fi
	#Wait for Cluster OK
	wait_for_weka_ok "$host"
done
log ""
#Add summary - Hosts Rebooted - Hosts Skipped - Drives Failed
log "Rebooted: $rebooted - Skipped: $skipped - Failed Drives: $failed_drives"
