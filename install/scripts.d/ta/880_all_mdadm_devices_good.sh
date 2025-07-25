#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check mdadm devices are consistent"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
REFERENCE="SFDC00018153"

RETURN_CODE=0

STATUS_FILE="/proc/mdstat"
if [ ! -e ${STATUS_FILE} ] ; then
    echo "No mdstat file - assuming ok"
    exit 0
fi

for MDADM_DEVICE in $(grep ^md[0-9] ${STATUS_FILE} | awk '{print $1}'); do
	# the format of /proc/mdstat isn't all that easy to parse, so use mdadm's test mode
	mdadm --detail --test /dev/${MDADM_DEVICE} >/dev/null 2>/dev/null
	if [ $? -ne 0 ] ; then
		RETURN_CODE=254
		echo "The madm device ${MDADM_DEVICE} did not report as OK. This can be caused by"
		echo "firmware or hardware problems and may lead to inconsistent data"
		echo "See ${REFERENCE} for more details"
	fi
done

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All mdadm devices report ok"
fi

exit ${RETURN_CODE}

### Example outputs:
#
#==================
## Sync in progress
#
#Personalities : [raid0] [raid1] [raid6] [raid5] [raid4] [raid10] 
#md0 : active raid1 sdc[1] sdb[0]
#      52395008 blocks super 1.2 [2/2] [UU]
#      [=================>...]  resync = 89.3% (46820352/52395008) finish=3.7min speed=24680K/sec
#      
#unused devices: <none>
#
#==================
## All ok
#
#
#Personalities : [raid0] [raid1] [raid6] [raid5] [raid4] [raid10] 
#md0 : active raid1 sdc[1] sdb[0]
#      52395008 blocks super 1.2 [2/2] [UU]
#      
#unused devices: <none>
#==================
## One device failed
#
#
#Personalities : [raid0] [raid1] [raid6] [raid5] [raid4] [raid10] 
#md0 : active raid1 sdb[0]
#      52395008 blocks super 1.2 [2/1] [U_]
      
#unused devices: <none>
