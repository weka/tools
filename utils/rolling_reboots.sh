#!/bin/bash
#Reboots all hosts - waits for rebuild before continuing and accepts a number of drive failures
#Logs results
#Requires passwordless root ssh
#Configuration:
HOST_LIST=./hosts
DRIVE_FAILURE_MAX=0 #Number of failed drives to tolerate
MIN_UPTIME=0 #Minutes - Skip recently rebooted hosts
S3_DRAIN_TIME=90 #Seconds
COMMENT_COMPLETED=true #Comment out host once complete as a checkpointing system.
CHECK_INTERVAL=30 #Seconds between drive/ssh/weka status checks.
CHECK_COUNT_LIMIT=5 #Times to check drives before rebooting again.
DRY_RUN=false #If true: don't actually drain S3 and reboot.
SKIP_IF_OFFLINE=true #Allow skipping hosts that are offline before we have interacted with them
LOG_DRIVE_IDS=true #Log Failed drive IDs
TRY_PCIE_RESCAN=true #Try rescanning PCIe bus before restarting on failed drives. Use only on actual NVMe drives
FAIL_ON_S3_DRAIN_FAIL=false #If S3 fails to drain for any reason (including host is not running S3) then fail out

LOG_FILE="$(basename "$0" | sed 's/\.[^.]*$//')_$(date '+%Y%m%d_%H%M%S').log"

trap clean_exit INT TERM
set -euo pipefail

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

	while true; do
	# Attempt to connect via SSH
		if ssh -o ConnectTimeout=5 -o BatchMode=yes "$host" "weka status" >/dev/null 2>&1; then
			log "CONTINUING: $host is online."
			return 0
		else
			log "WAITING:    $host is still offline"
			sleep $CHECK_INTERVAL
		fi
	done
}

wait_for_weka_ok() {
	#Loop infinitely as we must not continue if WEKA status is not OK, this can take hours depending on rebuilds.
	local host="$1"
	log "WAITING:    for WEKA Cluster to return to Status: OK"
	while true; do
		local status_output
		status_output=$(ssh "$host" 'weka status' 2>/dev/null)
		local status_line
		status_line=$(echo "$status_output" | grep -m 1 '^ *status: ' | sed 's/^ *s/S/' || echo "status: unknown")
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
	#set -x
	local host=$1
	local drive_info=$2
	local new_info=$3
	local failed
	failed=$(echo "$new_info" | grep -vw ACTIVE || true)
	echo "$failed" | while IFS= read -r drive; do
		local uid
		uid=$(echo "$drive" | awk '{print $2}')
		log "DRIVE:      Processing failed drive with UID: $uid" #parse $drive down to just uid

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
				# Execute SSH command and use command substitution to capture the result
				local ssh_output
				ssh_output=$(ssh -n "$host" "[ -d /sys/bus/pci/devices/$pci_id ] && echo 'present' || echo 'absent'")

				if [ "$ssh_output" == "present" ]; then
					log "DRIVE:      $uid is present in the PCIe bus. Removing it now."
					ssh -n "$host" "echo '1' > /sys/bus/pci/devices/$pci_id/remove"
				else
					log "DRIVE:      $uid is not present in the PCIe bus, a reboot may be required."
				fi
			else
				log "DRIVE:      Host mismatch for UID: $uid. Expected: $host, Found: $drive_host"
				log "FATAL:      Drive host mismatched, exiting!"
				echo -e "\a" #Ring the bell
				exit 3
			fi
		else
			log "DRIVE:      UID $uid is failed; It was not present before rebooting."
		fi
	done
	log "DRIVE:      Rescanning PCI bus"
	ssh "$host" "echo '1' > /sys/bus/pci/rescan"
	set +x
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
	if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$host" "exit" 2>/dev/null;then
		log "ERROR:      $host is offline"
		if [ "$SKIP_IF_OFFLINE" != true ];then
			log "FATAL:      Host is offline, set SKIP_IF_OFFLINE in the configuration section to allow continuing in this case"
			echo -e "\a" #Ring the bell
			exit 1;
		fi
	fi
	#Check uptime
	uptime_minutes=$(ssh "$host" "awk '{print int(\$1/60)}' /proc/uptime")
	if [ "$uptime_minutes" -lt "$MIN_UPTIME" ]; then
		log "SKIPPING:   $host due to host uptime being less than $MIN_UPTIME minutes."
		skipped=$((skipped + 1))
		continue
	fi
	#Get current drive count
	hostname=$(ssh "$host" "hostname")
	drive_count=$(ssh "$host" "weka cluster drive | grep -c \"${hostname}.* ACTIVE\" ||true" 2>/dev/null)
	status=wait_for_ok
	#Start loop
	#Check WEKA Status
	wait_for_weka_ok "$host"
	while [ "$status" != "good" ]; do
		#Save drive locations
		drive_info=$(ssh "$host" "weka cluster drive -v -o id,uid,path,hostname,status,serial| grep \"${hostname}\" || true")
		#Drain S3 & reboot - Needs checking
		if [ "$DRY_RUN" = false ];then
			log "---LIVE---: Draining and rebooting $host"
			if [ "$FAIL_ON_S3_DRAIN_FAIL" = true ]; then
				ssh -o ServerAliveInterval=1 -o ServerAliveCountMax=5 "$host" "
				weka s3 cluster drain \$(weka cluster container | awk '/frontend/ && /${hostname}/ {print \$1}') && \
				sleep ${S3_DRAIN_TIME} && \
				(sleep 1 && sudo shutdown -r now &>/dev/null &) &
				exit 0" || true
			else
				ssh -o ServerAliveInterval=1 -o ServerAliveCountMax=5 "$host" "
				weka s3 cluster drain \$(weka cluster container | awk '/frontend/ && /${hostname}/ {print \$1}') && \
				sleep ${S3_DRAIN_TIME}; \
				(sleep 1 && sudo shutdown -r now &>/dev/null &) &
				exit 0" || true
			fi
			rebooted=$((rebooted + 1))
		else
			log "DRY RUN:    Drain and reboot $host here"
			ssh "$host" "echo $host Frontend ID: \$(weka cluster container | awk '/frontend/ && /${hostname}/ {print \$1}')"
		fi
		#Wait for reboot
		sleep "$CHECK_INTERVAL"
		wait_for_ssh "$host"
		#Check drive count
		status=checking_drives
		sleep 3
		for ((j = 0; j < CHECK_COUNT_LIMIT; j++)); do
			for ((i = 0; i < CHECK_COUNT_LIMIT; i++)); do
				new_drive_info=$(ssh "$host" "weka cluster drive -v -o id,uid,path,hostname,status,serial| grep \"${hostname}\" || true")
				new_drives_count=$(echo "$new_drive_info" | grep -cw "ACTIVE" || true 2>/dev/null)
				drive_failures=$((drive_count - new_drives_count))
				if [ "$LOG_DRIVE_IDS" = true ] && [ "$drive_failures" -gt 0 ] && [ "$i" -gt 0 ];then
					log "INFO:       Failed Drive IDs:
$(echo "$new_drive_info" | grep -vw ACTIVE)"
				fi
				if [ "$drive_failures" -gt "$DRIVE_FAILURE_MAX" ]; then
					log "DRIVE:      $host has exceeded drive failure limit: $drive_failures failures"
					status=failed_drive_limit_exceeded
					sleep $CHECK_INTERVAL
				else
					log "CONTINUING: $host is within drive failure limit: $drive_failures failures"
					failed_drives=$((failed_drives + drive_failures))
					status=good
					break 2
				fi
			done
			#Do PCIe Rescan
			if [ "$TRY_PCIE_RESCAN" = true ];then
				pcie_rescan "$host" "$drive_info" "$new_drive_info"
			else
				break
			fi
		done
	done
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
