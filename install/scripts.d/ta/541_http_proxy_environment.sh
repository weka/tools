#!/bin/bash

DESCRIPTION="Check HTTP and HTTPS proxy variables in current session and /etc/environment"
SCRIPT_TYPE="??"

# Check environment variables in the current session
check_proxy_in_session() {
    local proxy_name=$1
    local proxy_value=$(env | grep -i "^$proxy_name=")

    if [ ! -z "$proxy_value" ]; then
        echo "$proxy_name is set in session to: $(echo $proxy_value | cut -d'=' -f2-)"
        proxy_not_set=0
    else
        echo "$proxy_name environment variable is not set in session"
    fi
}

# Check environment variables in /etc/environment
check_proxy_in_etc_environment() {
    local proxy_name=$1
    local proxy_value=$(grep -i "^$proxy_name" /etc/environment)

    if [ ! -z "$proxy_value" ]; then
        echo "$proxy_name is set in /etc/environment"
        proxy_not_set=0
    else
        echo "$proxy_name is not set in /etc/environment"
    fi
}

proxy_not_set=1

# Check for both lowercase and uppercase proxy environment variables in the session and /etc/environment
for proxy in http_proxy https_proxy; do
    check_proxy_in_session $proxy
    check_proxy_in_session ${proxy^^} # Check uppercase version
    check_proxy_in_etc_environment $proxy
    check_proxy_in_etc_environment ${proxy^^} # Check uppercase version
done

if [ $proxy_not_set -eq 1 ]; then
    echo 'No proxy environment variables are set in the current session or /etc/environment'
else
    echo 'At least one proxy environment variable is set in the current session or /etc/environment'
    rc="254"
fi

if [[ $ret -eq 0 ]]; then
  echo "Proxy check passed."
fi
exit $ret
