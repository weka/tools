#!/bin/bash

DESCRIPTION="Check HTTP and HTTPS proxy variables in current session and /etc/environment"
SCRIPT_TYPE="parallel-compare-backends"


check_proxy() {
    local proxy_name=$1
    local session_value=$(env | grep -i "^$proxy_name=")
    local etc_value=$(grep -i "^$proxy_name" /etc/environment)

    if [ ! -z "$session_value" ]; then
        echo "$proxy_name is set in session to: $(echo $session_value | cut -d'=' -f2-)"
        proxy_not_set=0
    else
        echo "$proxy_name environment variable is not set in session"
    fi

    if [ ! -z "$etc_value" ]; then
        echo "$proxy_name is set in /etc/environment"
        proxy_not_set=0
    else
        echo "$proxy_name is not set in /etc/environment"
    fi
}

proxy_not_set=1

# Check for both lowercase and uppercase proxy environment variables
for proxy in http_proxy https_proxy; do
    check_proxy $proxy
    check_proxy ${proxy^^} # Check uppercase version
done

if [ $proxy_not_set -eq 1 ]; then
    echo 'No proxy environment variables are set in the current session or /etc/environment'
    ret=0
else
    echo 'At least one proxy environment variable is set in the current session or /etc/environment'
    ret=254
fi

if [ $ret -eq 0 ]; then
  echo "Proxy check passed."
fi
exit $ret

