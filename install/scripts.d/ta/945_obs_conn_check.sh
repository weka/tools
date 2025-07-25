#!/bin/bash

#set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Basic OBS connectivity checks"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""

RETURN_CODE=0

declare -A OBS_CHECKED

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

##############################################################
# DNS / SOCKET CONNECTIVITY / RTT OUTLIER CHECKS

# Only perform this check on WEKA hosts w/ compute containers
if (weka local ps | grep -q -s compute); then
    while read OBS; do
        if [[ ${OBS} =~ hostname:([^,]*),id:([^,]*),obs_site:([^,]*),port:([^,]*),protocol:([^,]*), ]]; then
            OBS_HOST=${BASH_REMATCH[1]}
            OBS_ID=${BASH_REMATCH[2]}
            OBS_SITE=${BASH_REMATCH[3]}
            OBS_PORT=${BASH_REMATCH[4]}
            OBS_PROTOCOL=${BASH_REMATCH[5]}

            # For some reason, the port can be "0"
            if [[ ${OBS_PORT} == "0" ]]; then
                if [[ ${OBS_PROTOCOL} == "HTTP" ]]; then
                    OBS_PORT=80
                else
                    OBS_PORT=443
                fi
            fi

            # If we already checked this OBS endpoint, don't check it again
            if [[ -z "${OBS_CHECKED[$OBS_HOST]+x}" ]]; then

                # Only check OBS that are actively being used (i.e., associated with a fs)
                if (weka fs -J | grep ${OBS_ID} &>/dev/null); then
                    OBS_CHECKED["$OBS_HOST"]=1
                    declare -p OBS_CHECKED

                    # Perform DNS lookup
                    readarray -t OBS_IPS < <(dig "${OBS_HOST}" +short)

                    if [[ ${#OBS_IPS[@]} -eq 0 ]]; then
                        echo "WARN: No IPs returned for ${OBS_HOST}"
                        echo "Recommended action: validate DNS is operable."
                        RETURN_CODE=254
                    else
                        for IP in "${OBS_IPS[@]}"; do
                            # Perform simple socket check
                            if (! echo -n 2>/dev/null < /dev/tcp/${IP}/${OBS_PORT}); then
                                echo "WARN: Unable to establish connection to ${IP} on port ${OBS_PORT}"
                                echo "Recommended action: validate the endpoint is active and no firewall is blocking traffic."
                                RETURN_CODE=254
                            fi
                        done

                        # If this is a local OBS, check the RTT values
                        if [[ ${OBS_SITE} == "LOCAL" ]]; then
                            ################################################
                            # CHECK FOR OUTLYING RTT VALUES (experimental!)

                            # Temporary file to store IP and RTT info
                            tmpfile=$(mktemp)
                            for ip in "${OBS_IPS[@]}"; do
                                # Find lines in ss output matching the IP address and use the highest value
                                rtt_line=$(ss -tin | grep -A 1 -F "${ip}:${OBS_PORT}" | grep -woP 'rtt:\K[0-9.]+' | sort -rn | head -n1)
                                if [[ -n "$rtt_line" ]]; then
                                    echo "$ip $rtt_line" >> "$tmpfile"
                                fi
                            done

                            # Check if we got any RTT data
                            if [[ ! -s $tmpfile ]]; then
                                rm "$tmpfile"
                            else
                                # Use awk to calculate mean and standard deviation
                                status=$(awk '
                                {
                                    ip[$1] = $2;
                                    rtts[NR] = $2;
                                    sum += $2;
                                }
                                END {
                                    n = NR;
                                    mean = sum / n;

                                    for (i = 1; i <= n; i++) {
                                        diff = rtts[i] - mean;
                                        sumsq += diff * diff;
                                    }

                                    stddev = sqrt(sumsq / n);
                                    threshold = mean + 2 * stddev;

                                    for (ipaddr in ip) {
                                        rtt = ip[ipaddr];
                                        if (rtt > threshold) {
                                            print ipaddr, rtt
                                        }
                                    }
                                }
                                ' "$tmpfile") > bad_rtt.txt
                            fi

                            if [[ -s bad_rtt.txt ]]; then
                                while read ip rtt; do
                                    printf "WARN: Outlier RTT value found for OBS endpoint: %s (RTT: %.3f ms)\n" "$ip" "$rtt"
                                    printf "This may be indicative of a network connectivity issue.\n"
                                done < bad_rtt.txt
                                RETURN_CODE=254
                            fi
                            rm -f "$tmpfile" bad_rtt.txt
                        fi
                    fi
                fi
            fi
        fi
    done < <(
        weka fs tier s3 -J |
        grep -wE '(hostname|id|obs_site|port|protocol)' |
        paste - - - - - |
        tr -d ' \t\r\f\v' |
        sed 's/"//g'
    )
fi

#######################################################
# STATS CHECK FOR SERVER ERRORS (random-ish selection)

STATS_CHK=$(weka stats --start-time -30m --category object_storage \
    --stat RESPONSE_COUNT_BAD_GATEWAY \
    --stat RESPONSE_COUNT_GATEWAY_TIMEOUT \
    --stat RESPONSE_COUNT_HTTP_VERSION_NOT_SUPPORTED \
    --stat RESPONSE_COUNT_NOT_IMPLEMENTED \
    --stat RESPONSE_COUNT_SERVER_ERROR \
    --stat RESPONSE_COUNT_SERVICE_UNAVAILABLE \
    -Z \
    --process-ids $(weka cluster process -F hostname=$(hostname) -o id --no-header | paste -s -d,) \
    --per-process \
    --no-header)

if [[ -n ${STATS_CHK} ]]; then
    echo "WARN: One or more object_storage stats indicate server response error codes for this host."
    echo "This may or may not be indicative of an issue and requires further investigation."
    RETURN_CODE=254
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "Basic OBS connectivity checks passed."
fi
exit $RETURN_CODE