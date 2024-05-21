#!/usr/bin/env bash
dir=$(cd $(dirname $0);pwd)
this_file=$(basename $0)
pci_watchdog_py_path=${dir}/pci_watchdog.py
pci_watchdog_py_remote_path=/opt/weka/pci_watchdog.py

LOCAL_TOOLS=( weka )
REMOTE_TOOLS=( python3 nohup )
SERVERS_LIST=
SERVERS_LIST_COMMA=


if which pdsh >/dev/null 2>/dev/null;then
    echo "INFO pdsh found"
else
    echo "INFO pdsh not found using weka pdsh"
    WPDSH=1
fi

if [ "${WPDSH}"x = ""x ];then
    pdsh_wrapper() { echo "pdsh -S -R ssh -w ${SERVERS_LIST_COMMA}"; }
else
    echo "weka pdsh"
    pdsh_wrapper() { echo "weka debug pdsh --drives"; }
fi

if [ "${PDCP}"x != ""x ];then
    echo "INFO using pdcp"
    LOCAL_TOOLS=( ${LOCAL_TOOLS[@]} pdcp )
    REMOTE_TOOLS=( ${REMOTE_TOOLS[@]} pdcp )
fi


echo "INFO pdsh cmd: $(pdsh_wrapper)"


check_requirements() {
    local ret=0
    echo "INFO checking machine requirements"
    for t in ${LOCAL_TOOLS[@]};do
        if which ${t} 1>/dev/null 2>/dev/null ;then
            echo "INFO  ${t}... found"
        else
            echo "ERROR ${t}... missing"
            ret=1
        fi
    done
    if [ -f ${pci_watchdog_py_path} ];then
        echo "INFO  ${pci_watchdog_py_path}... found"
    else
        echo "ERROR ${pci_watchdog_py_path}... missing"
        ret=1
    fi

    if [ $(id -u) -eq 0 ];then
        echo "INFO  root... found"
    else
        echo "INFO  root... missing"
        ret=1
    fi
    return ${ret}
}

servers_list() {
    if [ "${WPDSH}"x != ""x ] && [ "${PDCP}"x = ""x ];then
        return 0
    fi
    # if not using weka pdsh calc the servers list

    if [ "${SERVERS_LIST_COMMA}"x != ""x ];then
        return 0
    fi
    echo "INFO identify cluster servers machines"
    while true;do
        [ "${SERVERS_LIST[@]}"x != ""x ] && break
        SERVERS_LIST=( $(weka cluster process -o hostname,role --no-header | grep -i drives | awk '{print $1}' | sort -u  | xargs | tr ' ' ',') )
        if [ $? -ne 0 ];then
            echo "ERROR failed to list servers"
            return 1
        fi
        if [ "${SERVERS_LIST[@]}"x = ""x ];then
            echo "ERROR no servers found"
            return 1
        fi
        break
    done
    SERVERS_LIST_COMMA=$(echo ${SERVERS_LIST[@]} | tr ' ' ',')
    if [ $? -ne 0 ] || [ "${SERVERS_LIST_COMMA}"x = ""x ];then
        SERVERS_LIST=""
        echo "ERROR failed to create servers list with comma: ${SERVERS_LIST_COMMA}"
        return 1
    fi
    echo "INFO servers: ${SERVERS_LIST[@]}"
    echo "INFO servers comma: ${SERVERS_LIST_COMMA}"
    return 0
}

# weka debug pdsh --drives "scp $(hostname):${pci_watchdog_py_path} ${pci_watchdog_py_remote_path}"

servers_requirements() {
    servers_list || return 1
    echo "INFO verify cluster servers requirements"

    $(pdsh_wrapper) "
set -euo pipefail
ret=0
for t in ${REMOTE_TOOLS[@]};do
    if which \${t} 1>/dev/null 2>/dev/null ;then
        echo \"INFO  \${t}... found\"
    else
        echo \"ERROR \${t}... missing\"
        ret=1
    fi
done

if [ \$(id -u) -eq 0 ];then
    echo \"INFO  root... found\"
else
    echo \"INFO  root... missing\"
    ret=1
fi

exit \${ret}
"
    return $?
}

servers_deploy() {
    echo "INFO deploy the $(basename ${pci_watchdog_py_path}) on cluster machines"

    servers_list || return 1

    local cp_res=0
    if [ "${PDCP}"x != ""x ];then
        pdcp -R ssh -w ${SERVERS_LIST_COMMA} ${pci_watchdog_py_path} ${pci_watchdog_py_remote_path}
        cp_res=$?
    else
        $(pdsh_wrapper) "scp $(hostname):${pci_watchdog_py_path} ${pci_watchdog_py_remote_path}"
        cp_res=$?
    fi

    if [ ${cp_res} -ne 0 ];then
        echo "ERROR failed to cp ${pci_watchdog_py_path} to one or more servers"
        return 1
    fi

    $(pdsh_wrapper) "
set -euo pipefail
if [ ! -f \"${pci_watchdog_py_remote_path}\" ];then
    echo \"ERROR failed to find ${pci_watchdog_py_remote_path}\"
    exit 1
fi
chmod +x ${pci_watchdog_py_remote_path} || exit 1
exit 0
"
    if [ $? -ne 0 ];then
        echo "ERROR failed to chmod +x ${pci_watchdog_py_remote_path} on one or more servers"
        return 1
    fi

    return 0
}

servers_start() {
    check_requirements || return 1
    servers_list || return 1
    servers_requirements || return 1
    servers_deploy || return 1

    echo "INFO start $(basename ${pci_watchdog_py_path}) on cluster machines"

    $(pdsh_wrapper) "
set -euo pipefail

verify_running() {
    [ ! -f ${pci_watchdog_py_remote_path}.pid ] && return 1
    PID=\$(cat ${pci_watchdog_py_remote_path}.pid)
    [ \"\${PID}\" = ""x ] && return 1
    kill -s 0 \${PID} >/dev/null 2>/dev/null && return 0
    rm ${pci_watchdog_py_remote_path}.pid
    return 1
}

if verify_running ;then
    echo \"INFO already running\"
    exit 0
fi

cd \$(dirname ${pci_watchdog_py_remote_path})
chmod +x ${pci_watchdog_py_remote_path}
nohup ${pci_watchdog_py_remote_path} >/dev/null 2>&1 &
PID=\$!
echo \"PID=\${PID}\"
echo \${PID} > ${pci_watchdog_py_remote_path}.pid
sleep 2

if ! verify_running ;then
    echo \"ERROR failed to start\"
    exit 1
fi

exit 0
"
    local res=$?
    if [ ${res} -ne 0 ];then
        echo "ERROR failed to start on one or more servers"
    fi
    echo "INFO log file at /opt/weka/logs/pci_watchdog.log on each one of servers"
    return ${res}
}

servers_stop() {
    servers_list || break

    echo "INFO stop $(basename ${pci_watchdog_py_path}) on cluster machines"

    $(pdsh_wrapper) "
set -euo pipefail

verify_running() {
    [ ! -f ${pci_watchdog_py_remote_path}.pid ] && return 1
    PID=\$(cat ${pci_watchdog_py_remote_path}.pid)
    [ \"\${PID}\" = ""x ] && return 1
    kill -s 0 \${PID} >/dev/null 2>/dev/null && return 0
    rm ${pci_watchdog_py_remote_path}.pid
    return 1
}

[ -f ${pci_watchdog_py_remote_path}.pid ] || exit 0

PID=\$(cat ${pci_watchdog_py_remote_path}.pid)

killsignal=\"SIGINT\"
for i in {1..6};do
    [ \$i -gt 3 ] && killsignal=\"-9\"
    echo \"INFO \${i}/6 PID=\${PID} stopping\"
    kill \${killsignal} \${PID} >/dev/null 2>/dev/null || true
    sleep 2
    verify_running || exit 0
done

echo \"ERROR failed to stop\"
exit 1
"
    local res=$?
    if [ ${res} -ne 0 ];then
        echo "ERROR failed to stop on one or more servers"
    fi
    return ${res}
}

usage() {
cat <<EOF

usage:
  ${this_file} <subcommand>

subcommands:
  check_requirements        verify local machine fit requirements
  servers_list              list the cluster candidate servers
  servers_requirements      verify cluster servers requirements
  servers_deploy            deploy the pci_watchdog.py on all cluster servers

  servers_start             start pci_watchdog.py on all cluster servers
  servers_stop              stop pci_watchdog.py on all cluster servers

notes:
  set env var WPDSH=1 to force use of weka debug pdsh
  set env var PDCP=1 to force use of pdcp

examples:
  WPDSH=1 PDCP=1 ${this_file} servers_start

EOF
}

main() {
    if [ "$1"x = ""x ] || [ "$1"x = "-h"x ] || [ "$1"x = "--help"x ];then
        usage
        return 0
    fi
    $@
    return $?
}

main $@
exit $?