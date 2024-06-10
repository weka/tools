#!/bin/bash                                                                                                                                                                                                                         

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check for at most one DNS entry for this hostname"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0


DIG_EXISTS=0
HOST_EXISTS=0
NSLOOKUP_EXISTS=0
NUMBER_OF_A_RECORDS=0
HOSTNAME=$(hostname)


if [[ $(type -P "dig") ]] ; then
    DIG_EXISTS=1
fi
if [[ $(type -P "host") ]] ; then
    HOST_EXISTS=1
fi
if [[ $(type -P "nslookup") ]] ; then
    NSLOOKUP_EXISTS=1
fi

if [[ $DIG_EXISTS -eq "1" ]] ; then
    NUMBER_OF_A_RECORDS=$(dig +short a ${HOSTNAME} | wc -l)
elif [[ $HOST_EXISTS -eq "1" ]] ; then
    NUMBER_OF_A_RECORDS=$(host -t a ${HOSTNAME} | wc -l)
elif [[ $NSLOOKUP_EXISTS -eq "1" ]] ; then
    # Last resort; rely on nslookup
    NUMBER_OF_A_RECORDS=$(nslookup ${HOSTNAME} | grep ^Address | grep -v '#' | wc -l)
else
    echo "Unable to check for number of A records due to missing utilities"
    echo "Please install one or more of dig/host/nslookup"
    exit 254 # warn
fi

if [[ ${NUMBER_OF_A_RECORDS} != "1" ]] ; then
    echo "There are ${NUMBER_OF_A_RECORDS} A records in DNS for ${HOSTNAME}"
    echo "This is very likely to cause problems with (at least) SMB-W clustering"
    RETURN_CODE=254
else
    echo "There is exactly one A record in DNS for ${HOSTNAME}"
    RETURN_CODE=0
fi

exit ${RETURN_CODE}
