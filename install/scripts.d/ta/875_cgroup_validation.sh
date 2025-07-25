#!/bin/bash

#set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Validate cgroup configuration"
SCRIPT_TYPE="parallel"
JIRA_REFERENCE="WEKAPP-482528"
WTA_REFERENCE=""
KB_REFERENCE=""
RETURN_CODE=0

# Internal reference:
#  https://www.notion.so/wekaio/cgroup-V2-support-8bdf2879c2974b7c8984cb4dfd037baf#18dd894b8aae4effb52b2a1b1504fadc

# Determine the current cgroup status, as indicated by weka agent
#   weka local status
#    Weka v4.4.4 (CLI build 4.4.4)
#    Cgroups: mode=auto, version=V2, enabled=false
if [[ $(weka local status 2>/dev/null | grep -i cgroup) =~ "mode="(.*)", version="(.*)", enabled="(.*) ]]; then
    AGENT_CGROUP_MODE=${BASH_REMATCH[1]}
    AGENT_CGROUP_VERSION=${BASH_REMATCH[2]}
    AGENT_CGROUP_ENABLED=${BASH_REMATCH[3]}
else
    echo "ERROR: Unable to parse Weka agent cgroup information."
    exit 255
fi

if [[ -z "$AGENT_CGROUP_MODE" || -z "$AGENT_CGROUP_VERSION" || -z "$AGENT_CGROUP_ENABLED" ]]; then
    echo "ERROR: Failed to parse Weka agent cgroup information."
    exit 255
fi

# Is the OS configured for cgroupv2, but not weka agent?
if [[ ${AGENT_CGROUP_MODE} == "auto" && ${AGENT_CGROUP_VERSION} == "V2" ]]; then
    echo "WARN: Weka agent cgroup mode \"auto\" will not enable cgroupv2 support."
    echo "Recommended Resolution: modify the /etc/wekaio/service.conf cgroups_mode from auto to force_v2"
    exit 254

# Does weka agent report cgroups are disabled?
elif [[ ${AGENT_CGROUP_ENABLED} == "false" ]]; then
    echo "WARN: Weka agent reports cgroups are not enabled."
    echo "Recommended Resolution: refer to KB-1234."
    exit 254

# Weka agent indicates cgroupv2 support is enabled
elif [[ ${AGENT_CGROUP_ENABLED} == "true" ]]; then
    for WEKA_CONTAINER in $(sudo weka local ps --output name --no-header | grep -e drive -e compute -e frontend); do

        if [[ ${AGENT_CGROUP_VERSION} == "V2" ]]; then
            ACTUAL_CPUS_RAW=$(cat /sys/fs/cgroup/weka-${WEKA_CONTAINER}/cpuset.cpus.effective)
        else
            ACTUAL_CPUS_RAW=$(cat /sys/fs/cgroup/cpuset/weka-${WEKA_CONTAINER}/cpuset.effective_cpus)
        fi
        
        ACTUAL_CPUS=()
        for entry in ${ACTUAL_CPUS_RAW//,/ }; do
            if [[ $entry == *-* ]]; then
                IFS='-' read -r start end <<< "$entry"
                    for ((i = start; i <= end; i++)); do
                        ACTUAL_CPUS+=("$i")
                    done
            else
                ACTUAL_CPUS+=("$entry")
            fi
        done

        # Filter out "auto" cores (i.e., those w/ a value of 4294967295)
        EXPECTED_CPUS=$(weka local resources -C ${WEKA_CONTAINER} --stable -J | grep core_id | grep -v 4294967295 | grep -oE '"core_id": [0-9]+' | awk '{print $2}')

        # Sanity check -- are arrays populated?
        if [[ ${#ACTUAL_CPUS} -eq 0 ]]; then
            echo "WARN: Weka CPUs for container ${WEKA_CONTAINER} may not be cgroup contrained."
            echo "Recommended Resolution: Contact Weka CST to help diagnose this discrepancy."
            RETURN_CODE=254
        elif [[ ${#EXPECTED_CPUS} -eq 0 ]]; then
            echo "WARN: Weka CPUs may be AUTO allocated for container ${WEKA_CONTAINER}, which is not recommended."
            echo "Recommended Resolution: Contact Weka CST to help diagnose this discrepancy."
            RETURN_CODE=254
        else
            MISSING_CPUS=()
            for cpu in $EXPECTED_CPUS; do
                if ! [[ " ${ACTUAL_CPUS[*]} " =~ " ${cpu} " ]]; then
                    MISSING_CPUS+=(${cpu})
                fi
            done

            if [[ ${#MISSING_CPUS[*]} -gt 0 ]]; then
                echo "WARN: The following cpus for container ${WEKA_CONTAINER} are not cgroup constrained: ${MISSING_CPUS[*]}"
                echo "Recommended Resolution: Contact Weka CST to help diagnose this discrepancy."
                RETURN_CODE=254
            fi
        fi
    done
fi


if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All Weka containers have consistent cgroup CPU restrictions"
fi

exit ${RETURN_CODE}