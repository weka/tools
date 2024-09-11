#!/bin/bash
# A condition can exist where all containers are up, cluster is formed, but not all containers have the same join secret(s) defined.
# This will cause the containers to not join the cluster upon their next restart (like during an upgrade).

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check to see if any running containers are missing a join secret"
SCRIPT_TYPE="single"
WTA_REFERENCE=""
KB_REFERENCE=""

# Check if we can run weka commands
weka status &> /dev/null
if [[ $? -ne 0 ]]; then
    echo "ERROR: Not able to run Weka commands."
    exit 254
elif [[ $? -eq 127 ]]; then
    echo "Weka not found."
    exit 254
elif [[ $? -eq 41 ]]; then
    echo "Unable to login into Weka cluster."
    exit 254
fi

# Initialize variables
USING_JOIN_SECRETS=False
REFERENCE_SECRET=""
MISMATCHED_CONTAINERS=()

# Loop through all container IDs
for CONTAINER_ID in $(weka cluster container -b --no-header -o id); do
  # Get the 'join_secret' for each container, sort the list of strings
  RESOURCES=$(weka cluster container resources "$CONTAINER_ID" -J | jq -c 'if .join_secret != null and (.join_secret | length > 0) then (.join_secret | sort) else empty end')

  # If any container has a non-empty 'join_secret', set USING_JOIN_SECRETS=True
  if [[ -n "$RESOURCES" ]]; then
    USING_JOIN_SECRETS=True

    # If REFERENCE_SECRET is not set, set it to the first valid sorted secret
    # If the first container is actually the outlier, all the other container IDs will be printed as 'wrong' at the end ¯\_(ツ)_/¯.
    if [[ -z "$REFERENCE_SECRET" ]]; then
      REFERENCE_SECRET="$RESOURCES"
    else
      # Compare the current secret with the REFERENCE_SECRET
      if [[ "$RESOURCES" != "$REFERENCE_SECRET" ]]; then
        # Add the container ID to the list of mismatched containers
        MISMATCHED_CONTAINERS+=("$CONTAINER_ID")
      fi
    fi
  fi
done

# Check if USING_JOIN_SECRETS is True
if [[ "$USING_JOIN_SECRETS" == "True" ]]; then
  if [[ ${#MISMATCHED_CONTAINERS[@]} -gt 0 ]]; then
    echo "ERROR: The following containers have different join secret lists: ${MISMATCHED_CONTAINERS[@]}"
    exit 1
  else
    echo "OK: All containers are using identical join secret lists."
    exit 0
  fi
else
  echo "OK: Join secrets are not in use."
  exit 0
fi
