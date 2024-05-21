#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check if tcp / udp connectivity works to a subset of the cluster leader's ports."
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Last modified: 2024-05-11

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

# Check if nc is installed
if ! nc -h &> /dev/null; then
  echo "nc is not installed"
  exit 254
fi

# Iterates over each cluster leader container / mgmt IP combination
while read ID; do
  while read IP; do
    PORT=$(weka cluster container resources $ID | awk '/Base Port/{print $3}')
    if [[ -n $PORT ]]; then
      if ! nc -z $IP $PORT &> /dev/null; then        # TCP Check
        RETURN_CODE=254
        echo "Unable to connect to $IP on tcp port $PORT."
      elif ! nc -z -u $IP $PORT &> /dev/null; then   # UDP Check
        RETURN_CODE=254
        echo "Unable to connect to $IP on udp port $PORT."
      fi
    else  # Could not query Base Port
      RETURN_CODE=254
    fi
  done < <(weka cluster container $ID --no-header -o ips | tr ',' '\n')
done < <(weka cluster container -F hostname=$(weka cluster container -L --no-header -o hostname) --no-header -o id)

if [[ $RETURN_CODE -eq 0 ]]; then
  echo "No port connectivity issues detected."
fi

exit ${RETURN_CODE}