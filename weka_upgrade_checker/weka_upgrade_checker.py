#!/usr/bin/env python3

import argparse
import re
import subprocess
import json
import time
import sys
import os
import datetime
import logging
from subprocess import Popen, PIPE, run
from distutils.version import LooseVersion as V
from io import StringIO
import concurrent.futures
import threading
import itertools
from itertools import chain
import tarfile

if sys.version_info < (3, 8):
    print("Must have python version 3.8 or later installed.")
    sys.exit(1)

pg_version = "1.2.6"

log_file_path = os.path.abspath("./weka_upgrade_checker.log")


logging.basicConfig(handlers=[logging.FileHandler(filename=log_file_path, encoding='utf-8', mode='w')],
                    format="%(asctime)s %(name)s:%(levelname)s:%(message)s",  datefmt="%F %A %T", level=logging.INFO)

if sys.stdout.encoding != 'UTF-8':
    if sys.version_info >= (3, 8):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding="utf-8")
    else:
        print("must run script using python3.8")
        sys.exit(1)

try:
    '❌ ✅'.encode(sys.stdout.encoding)
    unicode_test = True
except UnicodeEncodeError:
    unicode_test = False

if not unicode_test:
    [FAIL] = '\u274C'
    [PASS] = '\u2705'
    [WARN] = '\u26A0'
    [BAD] = '\u274C'


logger = logging.getLogger(__name__)


class colors:
    HEADER = '\033[95m'
    OKPURPLE = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def INFO(text):
    nl = '\n'
    print(f'{colors.OKPURPLE}{nl}{text}{nl}{colors.ENDC}')
    logging.info(text)


def INFO2(text):
    nl = '\n'
    print(f'{colors.OKCYAN}{nl}{text}{nl}{colors.ENDC}')
    logging.info(text)


def GOOD(text):
    print(f'{colors.OKGREEN}{text}{colors.ENDC}')
    logging.info(text)


def GOOD2(text):
    print(f'{colors.OKGREEN}✅ { text}{colors.ENDC}')
    logging.info(text)


def WARN(text):
    print(f'{colors.WARNING}{text}{colors.ENDC}')
    logging.warning(text)


def BAD(text):
    print(f'{colors.FAIL}{text}{colors.ENDC}')
    logging.debug(text)


class Host:
    def __init__(self, host_json):
        self.typed_id = str(host_json["host_id"])
        self.id = re.search("HostId<(\\d+)>", self.typed_id)[1]
        self.ip = str(host_json["host_ip"])
        self.port = str(host_json["mgmt_port"])
        self.hostname = str(host_json["hostname"])
        self.mode = str(host_json["mode"])
        self.is_up = host_json["status"]
        self.state = host_json["state"]
        self.sw_version = host_json["sw_version"]
        self.sw_release_string = (
            str(host_json["sw_release_string"])
            if "sw_release_string" in host_json
            else None
        )
        self.machine_id = str(host_json["machine_identifier"])
        self.mlx = (
            str(host_json["os_info"]["drivers"]["mlx5_core"])
            if "mlx5_core" in host_json
            else None
        )
        self.kernel_name = (
            str(host_json["os_info"]["kernel_name"])
            if "kernel_name" in host_json
            else None
        )
        self.kernel_release = (
            str(host_json["os_info"]["kernel_release"])
            if "kernel_release" in host_json
            else None
        )
        self.aws_zone = str(host_json["aws"]["availability_zone"])
        self.aws_id = str(host_json["aws"]["instance_id"])
        self.aws_type = str(host_json["aws"]["instance_type"])


class Machine:
    def __init__(self, machine_json):
        self.name = str(machine_json["name"])
        self.ip = str(machine_json["primary_ip_address"])
        self.port = str(machine_json["primary_port"])
        self.roles = str(machine_json["roles"])
        self.is_up = machine_json["status"]
        self.uid = str(machine_json["uid"])
        self.versions = machine_json["versions"][0]


class Spinner:
    def __init__(self, message, color=colors.OKCYAN):
        self.message = message
        self.color = color

    def start(self):
        self.running = True
        self.spinner_index = 0
        self.spinner_chars = [
            "         ",
            "▶        ",
            "▷▶       ",
            "▷▷▶      ",
            "▷▷▷▶     ",
            " ▷▷▶▶    ",
            "  ▷▶▶▶   ",
            "   ▶▶▶▶  ",
            "    ▶▶▶▶ ",
            "     ▶▶▶▶",
            "      ▶▶▶",
            "       ▶▶",
            "        ▶",
            "         ",
            "        ◀",
            "       ◀◁",
            "      ◀◁◁",
            "     ◀◁◁◁",
            "    ◀◀◁◁ ",
            "   ◀◀◀◁  ",
            "  ◀◀◀◀   ",
            " ◀◀◀◀    ",
            "◀◀◀◀     ",
            "◀◀◀      ",
            "◀◀       ",
            "◀        ",
            "         ",
        ]
        self.spinner_length = len(self.spinner_chars)

        def spin():
            while self.running:
                sys.stdout.write(
                    "\r"
                    + self.color
                    + self.message
                    + self.spinner_chars[self.spinner_index]
                    + "\r \b"
                )
                sys.stdout.flush()
                self.spinner_index = (
                    self.spinner_index + 1) % self.spinner_length
                time.sleep(0.1)

        self.spinner_thread = threading.Thread(target=spin)
        self.spinner_thread.start()

    def stop(self):
        self.running = False
        self.spinner_thread.join()
        sys.stdout.write(
            "\r" + " " * (len(self.message) +
                          len(self.spinner_chars) + 2) + "\r"
        )
        sys.stdout.flush()


def printlist(lst, num):
    for i in range(0, len(lst), num):
        if num == 6:
            WARN("⚠️  {} {} {} {} {} {}".format(*lst[i:i + num]))
            logging.warning("⚠️  {} {} {} {} {} {}".format(*lst[i:i + num]))
        elif num == 5:
            WARN("⚠️  {} {} {} {} {}".format(*lst[i:i + num]))
            logging.warning("⚠️  {} {} {} {} {}".format(*lst[i:i + num]))
        elif num == 4:
            WARN("⚠️  {} {} {} {}".format(*lst[i:i + num]))
            logging.warning("⚠️  {} {} {} {}".format(*lst[i:i + num]))
        elif num == 3:
            WARN("⚠️  {} {} {}".format(*lst[i:i + num]))
            logging.warning("⚠️  {} {} {}".format(*lst[i:i + num]))
        elif num == 2:
            WARN("⚠️  {} {}".format(*lst[i:i + num]))
            logging.warning("⚠️  {} {}".format(*lst[i:i + num]))
        elif num == 1:
            WARN("⚠️  {}".format(*lst[i:i + num]))
            logging.warning("⚠️  {}".format(*lst[i:i + num]))


def create_tar_file(source_file, output_path):
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    tar_file_name = f"{os.path.splitext(source_file)[0]}_{timestamp}.tar.gz"
    with tarfile.open(tar_file_name, "w:gz") as tar:
        tar.add(source_file)


def weka_cluster_checks():
    INFO("VERIFYING WEKA AGENT STATUS")
    weka_agent_service = subprocess.call(
        ["sudo", "service", "weka-agent", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if weka_agent_service != 0:
        BAD(
            '❌ Weka is NOT installed on host or the container is down, cannot continue'
        )
        sys.exit(1)
    else:
        GOOD('✅ Weka agent service is running')

    INFO("VERIFYING WEKA LOCAL CONTAINER STATUS")
    running_container = []
    con_status = json.loads(subprocess.check_output(
        ["weka", "local", "status", "-J"]))
    for container in con_status:
        if con_status[container]['type'] == "weka" and con_status[container]['isRunning']:
            GOOD('✅ Weka local container is running')
            running_container += [container]
            break
    else:
        BAD('❌ Weka local container is NOT running, cannot continue')
        sys.exit(1)

    INFO("WEKA USER LOGIN TEST")
    p = run(["weka", "status"], stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT)
    if p.returncode != 0:
        BAD('❌ Please login using weka user login first, cannot continue')
        sys.exit(1)
    else:
        GOOD('✅ Weka user login successful')

    INFO("WEKA IDENTIFIED")
    weka_info = json.loads(subprocess.check_output(["weka", "status", "-J"]))
    cluster_name = weka_info['name']
    weka_status = weka_info['status']
    uuid = weka_info['guid']
    weka_version = weka_info['release']
    GOOD(
        f"✅ CLUSTER:{cluster_name} STATUS:{weka_status} VERSION:{weka_version} UUID:{uuid}"
    )

    INFO("CHECKING FOR WEKA ALERTS")
    weka_alerts = subprocess.check_output(
        ["weka", "alerts", "--no-header"]).decode('utf-8').split('\n')
    if len(weka_alerts) == 0:
        GOOD('✅ No Weka alerts present')
    else:
        WARN(f'⚠️  {len(weka_alerts)} Weka alerts present')
        logging.warning(subprocess.check_output(
            ["weka", "alerts", "-J"]).decode('utf-8').split('\n'))

    INFO("CHECKING REBUILD STATUS")
    rebuild_status = json.loads(subprocess.check_output(
        ["weka", "status", "rebuild", "-J"]))
    if rebuild_status["progressPercent"] == 0:
        GOOD('✅ No rebuild in progress')
    else:
        WARN(
            f'⚠️  Rebuild in progress {rebuild_status["progressPercent"]} complete')

    if V("4.0") <= V(weka_version) < V("4.1"):
        INFO("VERIFYING WEKA BACKEND MACHINES")
        weka_bk_machines = [Machine(machine_json) for machine_json in json.loads(
            subprocess.check_output(["weka", "cluster", "machines", "list", "--role", "backend", "-J"]))]
        backend_hosts = [Host(host_json) for host_json in json.loads(
            subprocess.check_output(["weka", "cluster", "host", "-b", "-J"]))]
        ssh_bk_hosts = [{'name': w_bk_machine.name, 'ip': w_bk_machine.ip}
                        for w_bk_machine in weka_bk_machines if w_bk_machine.is_up != "DOWN"]
        down_bk_machine = []
        for w_bk_machine in weka_bk_machines:
            if w_bk_machine.is_up == "UP":
                continue
            down_bk_machine += [w_bk_machine.name,
                                w_bk_machine.ip, w_bk_machine.is_up]

        if not down_bk_machine:
            GOOD('✅ No failed hosts detected')
        else:
            WARN(f'Unhealthy backend hosts detected\n')
            printlist(down_bk_machine, 3)

    elif V(weka_version) >= V("4.1"):
        INFO("VERIFYING WEKA BACKEND MACHINES")
        weka_bk_servers = [Machine(machine_json) for machine_json in json.loads(
            subprocess.check_output(["weka", "cluster", "servers", "list", "--role", "backend", "-J"]))]
        backend_hosts = [Host(host_json) for host_json in json.loads(
            subprocess.check_output(["weka", "cluster", "container", "-b", "-J"]))]
        ssh_bk_hosts = [{'name': w_bk_server.name, 'ip': w_bk_server.ip}
                        for w_bk_server in weka_bk_servers if w_bk_server.is_up != "DOWN"]
        down_bk_servers = []
        for w_bk_server in weka_bk_servers:
            if w_bk_server.is_up == "UP":
                continue
            down_bk_servers += [w_bk_server.name,
                                w_bk_server.ip, w_bk_server.is_up]

        if not down_bk_servers:
            GOOD('✅ No failed hosts detected')
        else:
            WARN(f'Unhealthy backend hosts detected\n')
            printlist(down_bk_servers, 3)
    else:
        INFO("VERIFYING WEKA BACKEND HOST STATUS")
        backend_hosts = [Host(host_json) for host_json in json.loads(
            subprocess.check_output(["weka", "cluster", "host", "-b", "-J"]))]
        ssh_bk_hosts = [{'name': bkhost.hostname, 'ip': bkhost.ip}
                        for bkhost in backend_hosts if bkhost.is_up != "DOWN"]
        down_bkhost = []
        for bkhost in backend_hosts:
            if bkhost.is_up == "UP":
                continue
            down_bkhost += [bkhost.typed_id, bkhost.hostname,
                            bkhost.ip, bkhost.sw_version, bkhost.mode]

        if not down_bkhost:
            GOOD('✅ No failed hosts detected')
        else:
            WARN(f'Unhealthy backend hosts detected\n')
            printlist(down_bkhost, 5)

    if V("4.0") <= V(weka_version) < V("4.1"):
        INFO("VERIFYING WEKA CLIENT MACHINES")
        weka_cl_machines = [Machine(machine_json) for machine_json in json.loads(
            subprocess.check_output(["weka", "cluster", "machines", "list", "--role", "client", "-J"]))]
        client_hosts = [Host(host_json) for host_json in json.loads(
            subprocess.check_output(["weka", "cluster", "host", "-c", "-J"]))]
        ssh_cl_hosts = [{'name': w_cl_machine.name, 'ip': w_cl_machine.ip}
                        for w_cl_machine in weka_cl_machines if w_cl_machine.is_up]
        down_cl_machine = []
        for w_cl_machine in weka_cl_machines:
            if w_cl_machine.is_up == "UP":
                continue
            down_cl_machine += (w_cl_machine.name,
                                w_cl_machine.ip, w_cl_machine.is_up)

        if not down_cl_machine:
            GOOD('✅ No failed clients detected')
        else:
            WARN(f'Failed clients detected\n')
            printlist(down_cl_machine, 3)

    elif V(weka_version) >= V("4.1"):
        INFO("VERIFYING WEKA CLIENT MACHINES")
        weka_cl_servers = [Machine(machine_json) for machine_json in json.loads(
            subprocess.check_output(["weka", "cluster", "servers", "list", "--role", "client", "-J"]))]
        client_hosts = [Host(host_json) for host_json in json.loads(
            subprocess.check_output(["weka", "cluster", "container", "-c", "-J"]))]
        ssh_cl_hosts = [{'name': w_cl_server.name, 'ip': w_cl_server.ip}
                        for w_cl_server in weka_cl_servers if w_cl_server.is_up]
        down_cl_servers = []
        for w_cl_server in weka_cl_servers:
            if w_cl_server.is_up:
                continue
            down_cl_servers += [w_cl_server.name,
                                w_cl_server.ip, w_cl_server.is_up]

        if not down_cl_servers:
            GOOD('✅ No failed hosts detected')
        else:
            WARN(f'Unhealthy backend hosts detected\n')
            printlist(down_cl_servers, 3)

    else:
        INFO("VERIFYING WEKA CLIENT MACHINES")
        client_hosts = [Host(host_json) for host_json in json.loads(
            subprocess.check_output(["weka", "cluster", "host", "-c", "-J"]))]

        ssh_cl_hosts = [{'name': cl_host.hostname, 'ip': cl_host.ip}
                        for cl_host in client_hosts if cl_host.is_up != "DOWN"]

        down_clhost = []
        for client in client_hosts:
            if client.is_up == "UP":
                continue
            down_clhost += [client.typed_id, client.hostname,
                            client.ip[0], client.is_up, client.mode]

        if not down_clhost:
            GOOD('✅ No failed clients detected')
        else:
            WARN(f'Failed clients detected\n')
            printlist(down_clhost, 5)

    INFO("CHECKING CLIENT COMPATIBLE VERSIONS")
    try:
        sw_version = weka_version.split(".")
        check_version = '.'.join(sw_version[:2])
        cl_machine_need_upgrade = []
        cl_host_need_upgrade = []
        if V("4.0") <= V(weka_version) < V("4.1"):
            try:
                for w_cl_machine in weka_cl_machines:
                    clsw_version = w_cl_machine.versions.split(".")
                    if '.'.join(clsw_version[:2]) != check_version:
                        cl_machine_need_upgrade += [w_cl_machine.name,
                                                    w_cl_machine.ip]
            except NameError as e:
                WARN('⚠️  Unable to determine client weka version')

        elif V(weka_version) >= V("4.1"):
            try:
                for w_cl_server in weka_cl_servers:
                    clsw_version = w_cl_server.versions.split(".")
                    if '.'.join(clsw_version[:2]) != check_version:
                        cl_machine_need_upgrade += [w_cl_server.name,
                                                    w_cl_server.ip]
            except NameError as e:
                WARN('⚠️  Unable to determine client weka version')
        else:
            try:
                for client in client_hosts:
                    clsw_version = client.sw_version.split(".")
                    if '.'.join(clsw_version[:2]) != check_version:
                        cl_host_need_upgrade += [client.typed_id, client.hostname,
                                                 client.ip[0], client.is_up, client.mode]
            except NameError as e:
                WARN('⚠️  Unable to determine client weka version')
    except NameError as e:
        WARN('⚠️  Unable to determine client weka version')

    if V(weka_version) >= V("4.0"):
        if cl_machine_need_upgrade:
            WARN(
                f'Following client hosts must be upgraded to {weka_version} prior to weka upgrade\n')
            printlist(cl_machine_need_upgrade, 2)
        else:
            GOOD('✅ All clients hosts are up to date')
    elif not cl_host_need_upgrade:
        GOOD('✅ All clients hosts are up to date')
    else:
        WARN(
            f'Following client hosts must be upgraded to {weka_version} prior to weka upgrade\n')
        printlist(cl_host_need_upgrade, 5)

    INFO("VERIFYING WEKA NODE STATUS")
    weka_nodes = json.loads(subprocess.check_output(
        ["weka", "cluster", "nodes", "-J"]))
    down_node = []
    for node in weka_nodes:
        if node['status'] != "UP":
            down_node += [node['node_id'], node['hostname'],
                          node['status'], node['mode'], node['roles']]

    if not down_node:
        GOOD('✅ No failed hosts detected')
    else:
        WARN(f'Failed nodes detected\n')
        printlist(down_node, 5)

    # need to check element names
    INFO("VERIFYING WEKA FS SNAPSHOTS UPLOAD STATUS")
    weka_snapshot = json.loads(subprocess.check_output(
        ["weka", "fs", "snapshot", "-J"]))
    snap_upload = []
    for snapshot in weka_snapshot:
        if snapshot['stowStatus'] == "UPLOADING":
            snap_upload += [snapshot['id'], snapshot['filesystem'], snapshot['name'],
                            snapshot['remote_object_status'], snapshot['remote_object_progress']]

    if not snap_upload:
        GOOD('✅ Weka snapshot upload status ok')
    else:
        WARN(f'Following snapshots are uploading\n')
        printlist(snap_upload, 5)

    INFO("CHECKING FOR SMALL WEKA FILE SYSTEMS")
    wekafs = json.loads(subprocess.check_output(["weka", "fs", "-J"]))
    small_wekafs = []
    for fs in wekafs:
        if fs['available_total'] < 1073741824:
            small_wekafs += [fs['fs_id'], fs['group_name'],
                             fs['name'], fs['status'], fs['available_total']]

    if not small_wekafs:
        GOOD('✅ No small Weka file system found')
    else:
        WARN(f'Found small file systems\n')
        printlist(small_wekafs, 5)

    supported_ofed = {
        "3.12": [
            "4.7-1.0.0.1",
            "4.6-1.0.1.1",
            "4.5-1.0.1.0",
            "4.4-2.0.7.0",
            "4.4-1.0.0.0",
            "4.3-1.0.1.0",
            "4.2-1.2.0.0",
            "4.2-1.0.0.0",
            "4.7-3.2.9.0",
            "4.9-2.2.4.0",
            "5.0-2.1.8.0",
            "5.1-2.5.8.0",
            "5.1-2.6.2.0"
        ],
        "3.13": [
            "4.7-1.0.0.1",
            "4.6-1.0.1.1",
            "4.5-1.0.1.0",
            "4.4-2.0.7.0",
            "4.4-1.0.0.0",
            "4.3-1.0.1.0",
            "4.2-1.2.0.0",
            "4.2-1.0.0.0",
            "4.7-3.2.9.0",
            "4.9-2.2.4.0",
            "5.0-2.1.8.0",
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0"
        ],
        "3.14": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0"
        ],
        "4.0": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0",
            "5.8-1.1.2.1"
        ],
        "4.1": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.4-3.5.8.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0",
            "5.7-1.0.2.0",
            "5.8-1.1.2.1"
        ],
    }

    if V(weka_version) == V("3.12"):
        INFO("VERIFYING RAID REDUCTION SETTINGS")
        try:
            wekacfg = json.loads(subprocess.check_output(
                ["sudo", "weka", "local", "run", "--container", running_container[0], "--", "/weka/cfgdump"]))
            raid_reduction = wekacfg['clusterInfo']['reserved'][1]
            if raid_reduction == 1:
                GOOD('✅ Raid Reduction is disabled')
            else:
                WARN(
                    '⚠️  Raid Reduction is ENABLED issue command "weka debug jrpc config_override_key key="clusterInfo.reserved[1]" value=1" to disable'
                )
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN(f'⚠️  Unable able to determine Raid Reduction settings')

    if V(weka_version) == V("3.12"):
        INFO("VERIFYING TLS SECURITY SETTINGS")
        try:
            wekacfg = json.loads(subprocess.check_output(
                ["sudo", "weka", "local", "run", "--container", running_container[0], "--", "/weka/cfgdump"]))
            tls_security = wekacfg['clusterInfo']['reserved'][1]
            if tls_security == 1:
                GOOD(f'✅ Raid Reduction is disabled')
            else:
                WARN(
                    f'⚠️  Raid Reduction is ENABLED issue command "weka debug jrpc config_override_key key="clusterInfo.reserved[1]" value=1" to disable')
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN(f'⚠️  Unable able to determine Raid Reduction settings')

    if V("3.13") <= V(weka_version) < V("3.14"):
        INFO("VERIFYING UPGRADE ELIGIBILITY")
        link_type = weka_info['net']['link_layer']
        if link_type != "ETH":
            BAD(f'❌ Upgrading to 3.14 not supported. Requires Weka to use Ethernet connectivity. Please reach out to customer success on an ETA for IB support')
        elif ofed_downlevel:
            WARN(f'Upgrading to 3.14 requires Minimum OFED 5.1-2.5.8.0, following hosts need ofed updating\n')
            printlist(ofed_downlevel, 2)
        else:
            GOOD(f'✅ Upgrade eligibility to Weka version 3.14+ verified')

    if V("3.14") == V(weka_version) < V("3.14.2"):
        INFO("VERIFYING UPGRADE ELIGIBILITY")
        if link_type != "ETH":
            BAD(f'❌ Upgrading to 4.0 NOT supported. Requires Weka to use Ethernet connectivity and minimum Weka version 3.14.1 or greater')
        else:
            GOOD(f'✅ Cluster is upgrade eligible')

    if V(weka_version) == V("3.14"):
        weka_drives = json.loads(subprocess.check_output(
            ["weka", "cluster", "drive", "-J"]))
        if 'KIOXIA' in weka_drives:
            WARN(f'⚠️  Contact Weka Support prior to upgrading to Weka 4.0, System identified with Kioxia drives')
        else:
            GOOD(f'✅ No problematic drives found')

    if V(weka_version) == V("3.14"):
        INFO("VERIFYING SYSTEM OPTIMAL SETTINGS")
        WARN(f'⚠️  After upgrading to Weka 4.0.2, issue the following override command. "weka debug config override clusterInfo.allowDietAggressively false"')

    if V("4") <= V(weka_version) < V("4.04"):
        INFO("VERIFYING RAID REDUCTION SETTINGS")
        try:
            wekacfg = json.loads(subprocess.check_output(
                ["sudo", "weka", "local", "run", "--container", running_container[0], "--", "/weka/cfgdump"]))
            raid_reduction = wekacfg['clusterInfo']['allowDietAggressively']
            if not raid_reduction:
                GOOD(f'✅ Raid Reduction is disabled')
            else:
                WARN(
                    f'⚠️  Raid Reduction is ENABLED. Please contact Weka support for instructions on how to disable')
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN(f'⚠️  Unable able to determine Raid Reduction settings')

    if V(weka_version) == V("3.9"):
        INFO("VERIFYING BUCKET L2BLOCK ENTRIES")
        compute_node = []
        spinner = Spinner('  Processing Data   ', color=colors.OKCYAN)
        spinner.start()
        try:
            weka_nodes = json.loads(subprocess.check_output(
                ["weka", "cluster", "nodes", "-J"]))
            for node in weka_nodes:
                if node['roles'] == ['COMPUTE'] and node['status'] == "UP":
                    compute_node += (re.findall(r'\d+', node['node_id']))
            buckets = {}
            for id in compute_node:
                buckets |= json.loads(
                    subprocess.check_output(
                        [
                            "weka",
                            "debug",
                            "manhole",
                            "--node",
                            id,
                            "buckets_get_registry_stats",
                        ],
                        stderr=subprocess.PIPE,
                    )
                )
            bucket_list = [[key, val] for key, val in buckets.items()]
            error_bucket = []
            for bucket in bucket_list:
                if bucket[1]['entriesInL2Block']['max'] > 477:
                    error_bucket += bucket
            if error_bucket:
                WARN(
                    f'⚠️  L2BLOCK error entries found, please contact weka support ref WEKAPP-229504\n')
                for line in error_bucket:
                    WARN(str(line))
            else:
                GOOD(f'✅ No error L2BLOCK entries found')
        except Exception as e:
            WARN(f'⚠️  Unable able to determine entriesInL2Block entries {e}')

        spinner.stop()

    INFO("VERIFYING SSD FIRMWARE")
    weka_drives = json.loads(subprocess.check_output(
        ["weka", "cluster", "drive", "-J"]))
    bad_firmware = []
    for drive in weka_drives:
        if drive['firmware'] == "EDB5002Q":
            bad_firmware += [drive['disk_id'], drive['node_id'],
                             drive['status'], drive['firmware'], drive['hostname']]

    if not bad_firmware:
        GOOD(f'✅ SSD Firmware check completed')
    else:
        WARN(f'⚠️  The following SSDs might be problematic please contact Weka Support\n')
        printlist(bad_firmware, 5)

    INFO("VERIFYING WEKA CLUSTER DRIVE STATUS")
    weka_drives = json.loads(subprocess.check_output(
        ["weka", "cluster", "drive", "-J"]))
    bad_drive = []
    for drive in weka_drives:
        if drive['status'] != "ACTIVE":
            bad_drive += [drive['disk_id'], drive['node_id'],
                          drive['status'], drive['firmware'], drive['hostname']]

    if not bad_drive:
        GOOD(f'✅ All drives are in OK status')
    else:
        WARN(f'The following Drives are not Active\n')
        printlist(bad_drive, 5)

    INFO("VERIFYING WEKA TRACES STATUS")
    if V(weka_version) >= V("3.10"):
        weka_traces = json.loads(subprocess.check_output(
            ["weka", "debug", "traces", "status", "-J"]))
        if weka_traces['enabled']:
            GOOD(f'✅ Weka traces are enabled')
        else:
            WARN(
                f'⚠️  Weka traces are NOT enabled, enable Weka traces using "weka debug traces start"')
    else:
        weka_traces = subprocess.check_output(
            ["sudo", "weka", "local", "exec", "/usr/local/bin/supervisorctl", "status", "weka-trace-dumper"]).decode(
            'utf-8')
        if "RUNNING" in weka_traces:
            GOOD(f'✅ Weka traces are enabled')
        else:
            WARN(f'⚠️  Weka traces are NOT enabled, enable Weka traces using "weka local exec /usr/local/bin/supervisorctl stop weka-trace-dumper"')

    if V(weka_version) >= V("3.9"):
        INFO("CHECKING FOR MANUAL WEKA OVERRIDES")
        override_list = []
        if manual_overrides := json.loads(
            subprocess.check_output(
                ["weka", "debug", "override", "list", "-J"])
        ):
            WARN("Manual Weka overrides found")
            for override in manual_overrides:
                override_list += [override['override_id'], override['key'],
                                  override['value'], override['bucket_id'], override['enabled']]

        else:
            GOOD(f'✅ No manual Weka overrides found')
    if override_list:
        printlist(override_list, 5)

    INFO("CHECKING FOR WEKA BLACKLISTED NODES")
    blacklist = []
    if weka_info['nodes']['blacklisted'] == 0:
        GOOD(f'✅ No Weka blacklisted nodes found')
    else:
        WARN(f'Weka blacklisted nodes found\n')
        blacklist_list = json.loads(subprocess.check_output(
            ["weka", "debug", "blacklist", "list", "-J"]))
        for nodes in blacklist_list:
            blacklist += [nodes['node_id'], nodes['hostname'],
                          nodes['ips'], nodes['status'], nodes['network_mode']]

    if blacklist:
        printlist(blacklist, 5)

    if V(weka_version) >= V("3.14"):
        INFO("CHECKING WEKA STATS RETENTION")
        stats_retention = json.loads(subprocess.check_output(
            ["weka", "stats", "retention", "status", "-J"]))
        if stats_retention['retention_secs'] <= 172800:
            GOOD(f'✅ Weka stats retention settings are set correctly')
        else:
            WARN(
                f'⚠️  Set stats retention to 1 days, execute "weka stats retention set --days 1". Following the upgrade revert back using "weka stats retention set --days {int(stats_retention["retention_secs"] / 86400)}')

    if V(weka_version) >= V("3.12") and weka_info['hosts']['total_count'] >= 100:
        INFO("VERIFYING TLS SETTINGS")
        try:
            wekacfg = json.loads(subprocess.check_output(
                ["sudo", "weka", "local", "run", "--container", running_container[0], "--", "/weka/cfgdump"]))
            if (wekacfg['serializedTLSData']['state']) == "NONE":
                GOOD(f'✅ TLS is Disabled')
            else:
                WARN(
                    f'⚠️  TLS is Enabled and should be disabled please contact Weka Support')
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN(f'⚠️  Unable able to determine TLS state')

    INFO("VERIFING HOSTS MACHINE IDENTIFIERS")
    spinner = Spinner('  Retrieving Data  ', color=colors.OKCYAN)
    spinner.start()

    host_machine_identifiers = {}

    for bkhost in backend_hosts:
        hostname = bkhost.hostname
        machine_id = bkhost.machine_id
        host_machine_identifiers[hostname] = machine_id

    for clhost in client_hosts:
        hostname = clhost.hostname
        machine_id = clhost.machine_id
        host_machine_identifiers[hostname] = machine_id

    rev_dict = {}
    for key, value in host_machine_identifiers.items():
        rev_dict.setdefault(value, set()).add(key)

    duplicate_identifiers = set(
        chain.from_iterable(
            values for key, values in rev_dict.items() if len(values) > 1
        )
    )

    if duplicate_identifiers:
        BAD(f'{" " * 5}❌ Duplicate machine identifiers found for hosts:')
        for hostname in duplicate_identifiers:
            BAD(f'{" " * 10}-> {hostname}')
    else:
        GOOD(f'{" " * 5}✅ Machine identifiers check complete')

    spinner.stop()

    s3_cluster_status = json.loads(
        subprocess.check_output(["weka", "s3", "cluster", "-J"]))
    if s3_cluster_status['active']:
        bad_s3_hosts = []
        failed_s3host = []
        INFO("CHECKING WEKA S3 CLUSTER HEALTH")
        s3_cluster_hosts = json.loads(subprocess.check_output(
            ["weka", "s3", "cluster", "status", "-J"]))
        for host, status in s3_cluster_hosts.items():
            if not status:
                bad_s3_hosts.append([host])

        if not bad_s3_hosts:
            GOOD("No failed s3 hosts found")
        else:
            WARN("Found s3 cluster hosts in not ready status\n")
            for s3host in bad_s3_hosts:
                for bkhost in backend_hosts:
                    if s3host == bkhost.typed_id:
                        failed_s3host += [bkhost.typed_id, bkhost.hostname,
                                          bkhost.ip, bkhost.sw_version, bkhost.mode]

        printlist(failed_s3host, 5)

    INFO("VALIDATING BACKEND SUPPORTED NIC DRIVERS INSTALLED")
    spinner = Spinner('  Processing Data   ', color=colors.OKCYAN)
    spinner.start()

    backend_ips = [*{bkhost.ip for bkhost in backend_hosts}]

    backend_host_names = [*{bkhost.hostname for bkhost in backend_hosts}]

    hostname_from_api = []

    cmd = ["weka", "cluster", "host", "info-hw", "-J"]

    host_hw_info = json.loads(subprocess.check_output(cmd + backend_ips))

    ofed_downlevel = []
    current_version = {}

    for key, val in host_hw_info.items():
        if host_hw_info.get(key) is not None:
            try:
                if 'Mellanox Technologies' not in (str(val['eths'])):
                    break
                key = [
                    *{bkhost.hostname for bkhost in backend_hosts if key == bkhost.ip}][0]
                current_version[key] = []
                result = (val['ofed']['host'])
                current_version[key].append(result)
                hostname_from_api += [key]
                if (V(result)) < (V("5.1-2.5.8.0")):
                    ofed_downlevel += (key, result)
                if result not in supported_ofed[check_version]:
                    BAD(
                        f'{" " * 5}❌ Host: {key} on weka version {weka_version} does not support OFED version {result}'
                    )
                else:
                    GOOD(
                        f'{" " * 5}✅ Host: {key} on weka version {weka_version} is running supported OFED version {result}'
                    )
            except Exception as e:
                pass

    for bkhostnames in hostname_from_api:
        if bkhostnames in backend_host_names:
            backend_host_names.remove(bkhostnames)

    if not current_version:
        GOOD(f'{" " * 5}✅ Mellanox nics not found')
    elif backend_host_names != []:
        for bkhostname in backend_host_names:
            WARN(
                f'{" " * 5}⚠️ Unable to determine Host: {bkhostname} OFED version'
            )
    elif (len(set(current_version)) == 1):
        WARN(f'\n{" " * 5}⚠️  Mismatch ofed version found on backend hosts\n')
        printlist(printlist, 1)

    spinner.stop()

    # need to understand how to handle exception.
    if s3_cluster_status['active']:
        if V(weka_version) < V("4.1"):
            INFO("CHECKING ETCD ENDPOINT HEALTH")
            spinner = Spinner('  Retrieving Data  ', color=colors.OKCYAN)
            spinner.start()

            if s3_cluster_status['active']:
                etcd_status = []
                output = None
                retcode = subprocess.call(["sudo", "weka", "local", "exec", "-C", "s3", "etcdctl", "endpoint",
                                        "health", "--cluster", "-w", "json"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

                if retcode == 0:
                    if etcd_status := json.loads(
                        subprocess.check_output(
                            [
                                "sudo",
                                "weka",
                                "local",
                                "exec",
                                "-C",
                                "s3",
                                "etcdctl",
                                "endpoint",
                                "health",
                                "--cluster",
                                "-w",
                                "json",
                            ]
                        )
                    ):
                        for status in etcd_status:
                            if not status["health"]:
                                WARN(
                                    f'{" " * 5}⚠️  ETCD member on {status["endpoint"]} is down')
                            else:
                                GOOD(
                                    f'{" " * 5}✅ ETCD members are healthy {status["endpoint"]}')
                else:
                    WARN(
                        f'{" " * 5}⚠️  ETCD DB is not healthy or not running please contact Weka support'
                    )

            spinner.stop()

    return backend_hosts, ssh_bk_hosts, client_hosts, ssh_cl_hosts, weka_info, check_version, backend_ips


supported_os = {
    "3.12": {
        "backends_clients": {
            "centos": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2"
            ],
            "rhel": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2"
            ],
            "rocky": [],
            "sles": [],
            "ubuntu": [
                "18.04.0",
                "18.04.1",
                "18.04.2",
                "18.04.3",
                "18.04.4",
                "18.04.5",
                "20.04.0",
                "20.04.1"
            ],
            "amzn": [
                "17.09",
                "17.12",
                "18.03",
                "2"
            ],
        },
        "clients_only": {
            "sles": [
                "12.5",
                "15.2"
            ],
        },
    },
    "3.13": {
        "backends_clients": {
            "centos": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5"
            ],
            "rhel": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5",
                "8.6",
                "8.7"
            ],
            "rocky": [
                "8.6",
                "8.7"
            ],
            "sles": [],
            "ubuntu": [
                "18.04.0",
                "18.04.1",
                "18.04.2",
                "18.04.3",
                "18.04.4",
                "18.04.5",
                "18.04.6",
                "20.04.0",
                "20.04.1",
            ],
            "amzn": [
                "17.09",
                "17.12",
                "18.03",
                "2"],
        },
        "clients_only": {
            "sles": [
                "12.5",
                "15.2"
            ],
        },
    },
    "3.14": {
        "backends_clients": {
            "centos": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5"
            ],
            "rhel": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5",
                "8.6",
                "8.7"
            ],
            "rocky": [
                "8.6",
                "8.7"
            ],
            "sles": [],
            "ubuntu": [
                "18.04.0",
                "18.04.1",
                "18.04.2",
                "18.04.3",
                "18.04.4",
                "18.04.5",
                "18.04.6",
                "20.04.0",
                "20.04.1"
            ],
            "amzn": [
                "17.09",
                "17.12",
                "18.03",
                "2"
            ],
        },
        "clients_only": {
            "sles": [
                "12.5",
                "15.2"
            ],
        },
    },
    "4.0": {
        "backends_clients": {
            "centos": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5",
            ],
            "rhel": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5",
                "8.6",
                "8.7"
            ],
            "rocky": [
                "8.6",
                "8.7"
            ],
            "sles": [],
            "ubuntu": [
                "18.04.0",
                "18.04.1",
                "18.04.2",
                "18.04.3",
                "18.04.4",
                "18.04.5",
                "18.04.6",
                "20.04.0",
                "20.04.1",
                "20.04.2",
                "20.04.3",
                "20.04.4"
            ],
            "amzn": [
                "17.09",
                "17.12",
                "18.03",
                "2"
            ],
        },
        "clients_only": {
            "sles": [
                "12.5",
                "15.2"
            ],
        },
    },
    "4.1": {
        "backends_clients": {
            "centos": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5"
            ],
            "rhel": [
                "7.2",
                "7.3",
                "7.4",
                "7.5",
                "7.6",
                "7.7",
                "7.8",
                "7.9",
                "8.0",
                "8.1",
                "8.2",
                "8.3",
                "8.4",
                "8.5",
                "8.6",
                "8.7"
            ],
            "rocky": [
                "8.6",
                "8.7"
            ],
            "sles": [],
            "ubuntu": [
                "18.04.0",
                "18.04.1",
                "18.04.2",
                "18.04.3",
                "18.04.4",
                "18.04.5",
                "18.04.6",
                "20.04.0",
                "20.04.1",
                "20.04.2",
                "20.04.3",
                "20.04.4",
                "20.04.5"
            ],
            "amzn": [
                "17.09",
                "17.12",
                "18.03",
                "2"
            ],
        },
        "clients_only": {
            "sles": [
                "12.5",
                "15.2"
            ],
        },
    },
}


def ssh_check(host_name, result, ssh_bk_hosts):
    passwordless_ssh = result
    if passwordless_ssh != 0:
        BAD(
            f'{" " * 5}❌ Password SSH not configured on host: {host_name}, will exclude from checks'
        )
        ssh_bk_hosts = [x for x in ssh_bk_hosts if x['name'] != host_name]
    else:
        GOOD(f'{" " * 5}✅ Password SSH configured on host: {host_name}')

    return ssh_bk_hosts


def check_os_release(host_name, result, weka_version, check_version, backend=True, client=False):
    if "CentOS" in result:
        result = result.split()
        result = result[3]
        version = result.split('.')
        version = '.'.join(version[:2])

        if backend:
            if version not in supported_os[check_version]['backends_clients']['centos']:
                BAD(
                    f'{" " * 5}❌ Host {host_name} OS {"centos"} {version} is not supported with weka version {weka_version}'
                )
            else:
                GOOD(
                    f'{" " * 5}✅ Host {host_name} OS {"centos"} {version} is supported with weka version {weka_version}'
                )
        elif client:
            if version not in supported_os[check_version]['backends_clients']['centos'] and supported_os[check_version]['clients_only']['centos']:
                BAD(
                    f'{" " * 5}❌ Host {host_name} OS {"centos"} {version} is not supported with weka version {weka_version}'
                )
            else:
                GOOD(
                    f'{" " * 5}✅ Host {host_name} OS {"centos"} {version} is supported with weka version {weka_version}'
                )
    else:
        info_str = (result).replace("=", ":")
        info_list = info_str.split('\n')
        info_list = [item for item in info_list if item]

        dict_info = {}
        for item in info_list:
            key, value = item.split(':', 1)
            dict_info[key] = value.strip('"')

        if dict_info['ID'] == "ubuntu":
            version = re.search(r'\b\d+\.\d+\.\d+\b',
                                dict_info['VERSION']).group()
        elif dict_info['ID'] == "rocky" or "rhel":
            version = dict_info['VERSION_ID']
        else:
            version = dict_info['VERSION']

        if backend:
            if version not in supported_os[check_version]['backends_clients'][dict_info['ID']]:
                BAD(
                    f'{" " * 5}❌ Host {host_name} OS {dict_info["ID"]} {version} is not supported with weka version {weka_version}'
                )
            else:
                GOOD(
                    f'{" " * 5}✅ Host {host_name} OS {dict_info["ID"]} {version} is supported with weka version {weka_version}'
                )
        elif client:
            if version not in supported_os[check_version]['backends_clients'][dict_info['ID']] and supported_os[check_version]['clients_only'][dict_info['ID']]:
                BAD(
                    f'{" " * 5}❌ Host {host_name} OS {dict_info["ID"]} {version} is not supported with weka version {weka_version}'
                )
            else:
                GOOD(
                    f'{" " * 5}✅ Host {host_name} OS {dict_info["ID"]} {version} is supported with weka version {weka_version}'
                )


def weka_agent_check(host_name, result):
    weka_agent_status = result
    if weka_agent_status != 0:
        BAD(f'{" " * 5}❌ Weka Agent Service is NOT running on host: {host_name}')
    else:
        GOOD(f'{" " * 5}✅ Weka Agent Service is running on host: {host_name}')


def time_check(host_name, result):
    current_time = result
    local_lime = int(time.time())
    if abs(int(current_time) - local_lime) > 60:
        BAD(f'{" " * 5}❌ Time difference greater than 60s on host: {host_name}')
    else:
        GOOD(f'{" " * 5}✅ Time check passed on host: {host_name}')


def client_mount_check(host_name, result):
    if int(result) > 0:
        BAD(f'{" " * 5}❌ Found wekafs mounted on /weka for host: {host_name}')
    else:
        GOOD(f'{" " * 5}✅ No wekafs mounted on /weka for host: {host_name}')


def free_space_check_data(host_name, results):
    results_by_host = {}
    for host_name, result in results:
        if host_name not in results_by_host:
            results_by_host[host_name] = []
        results_by_host[host_name].append((result).strip())

    for result in results_by_host.items():
        hname = result[0]
        weka_partition = int(result[1][0])
        weka_data_dir = int(result[1][1])
        free_capacity_needed = (weka_data_dir * 1.5)
        if (free_capacity_needed) > (weka_partition):
            WARN(
                f'{" " * 5}⚠️  Host: {hname} does not have enough free capacity, need to free up ~{(free_capacity_needed - weka_partition) / 1000}G'
            )
        else:
            GOOD(f'{" " * 5}✅ Host: {hname} has adequate free space')


def free_space_check_logs(results):
    for result in results:
        hname = result[0]
        result = result[1].split(" ")
        logs_partition_used = int(result[0])
        free_capacity_needed = (logs_partition_used * 1.5)
        logs_partition_available = int(result[1])
        if (free_capacity_needed) > (logs_partition_available):
            WARN(
                f'{" " * 5}⚠️  Host: {hname} does not have enough free capacity, need to free up ~{(free_capacity_needed - logs_partition_available) / 1000}G'
            )
        else:
            GOOD(f'{" " * 5}✅ Host: {hname} has adequate free space')


def weka_container_status(results, weka_version):
    containers_by_host = {
        host: [
            {
                'name': containers['name'],
                'isRunning': containers['isRunning'],
                'isDisabled': containers['isDisabled'],
                'type': containers['type'],
            }
            for containers in result
        ]
        for host, result in results
    }
    for host in containers_by_host.items():
        host_name = host[0]
        containers = host[1]
        INFO2(f'{" " * 2}Checking weka container status on host {host_name}:')
        for container in containers:
            name = container['name']
            is_running = container['isRunning']
            is_disabled = container['isDisabled']
            container_status = "Running" if is_running else "Stopped"
            disabled = "True" if is_disabled else "False"
            if V(weka_version) >= V("4.1"):
                if disabled == "True" or container_status == "Stopped" or name == "upgrade":
                    BAD(f'{" " * 5}❌ Container {name}: {container_status} and Disabled={disabled}')
                else:
                    GOOD(
                        f'{" " * 5}✅ Container {name}: {container_status} and Disabled={disabled}')
            else:
                type = container['type']
                if type == "weka" and disabled == "False" or container_status == "Running":
                    GOOD(
                        f'{" " * 5}✅ Container {name}: {container_status} and Disabled={disabled}')
                elif name == "upgrade":
                    BAD(f'{" " * 5}❌ Container {name}: {container_status} and Disabled={disabled}')
                elif type != "weka" and disabled == "False":
                    BAD(f'{" " * 5}❌ Container {name}: {container_status} and Disabled={disabled}')


def weka_mounts(results):
    new_results = (dict(results))
    for item in new_results.items():
        host_name = item[0]
        mounts = (item[1].split('\n'))
        INFO2(f'{" " * 2} Checking for mounted Weka filesystems on host {host_name}:')
        if mounts == ['']:
            GOOD(f'{" " * 5}✅ No mounted Weka filesystems found')
        else:
            for mount in mounts:
                WARN(f'{" " * 5}⚠️  Found Weka filesytems mounted {mount}')


def get_host_name(host_id, backend_hosts):
    return next(
        (
            bkhost.hostname
            for bkhost in backend_hosts
            if host_id == bkhost.typed_id
        ),
        "",
    )


def frontend_check(host_name, result):
    frontend_mounts = result
    if frontend_mounts != '0':
        WARN(f'{" " * 5}⚠️  Weka Frontend Process in use on host: {host_name}, contact Weka Support prior to upgrading')
    else:
        GOOD(f'{" " * 5}✅ Weka Frontend Process OK on host: {host_name}')


def protocol_host(backend_hosts):
    S3 = []
    if s3_cluster_status := json.loads(
        subprocess.check_output(["weka", "s3", "cluster", "-J"])
    ):
        if s3_cluster_status['active']:
            weka_s3 = json.loads(subprocess.check_output(
                ["weka", "s3", "cluster", "status", "-J"]))
            if weka_s3 != []:
                S3 = list(weka_s3)

    weka_smb = json.loads(subprocess.check_output(
        ["weka", "smb", "cluster", "-J"]))
    SMB = list(weka_smb['sambaHosts']) if weka_smb != [] else []
    NFS = []
    weka_nfs = json.loads(subprocess.check_output(
        ["weka", "nfs", "interface-group", "-J"]))
    if weka_nfs != []:
        NFS = [hid['host_id']
               for host_id in weka_nfs for hid in host_id['ports']]

    combined_lists = [S3, SMB, NFS]

    total_protocols = {}
    protocol_type = ['s3', 'smb', 'nfs']

    for i, lst in enumerate(combined_lists):
        for elem in lst:
            if elem in total_protocols:
                total_protocols[elem]['freq'] += 1
                total_protocols[elem]['lists'].append(protocol_type[i])
            else:
                total_protocols[elem] = {
                    'freq': 1, 'lists': [protocol_type[i]]}

        multiprotocols = {
            bkhost.hostname: total_protocols[bkhost.typed_id]
            for bkhost in backend_hosts
            if bkhost.typed_id in total_protocols
        }

    protocol_host_names = [
        bkhost.hostname
        for bkhost in backend_hosts
        if bkhost.hostname not in total_protocols
    ]

    protocol_host_names = list(dict.fromkeys(protocol_host_names))

    for host_name in multiprotocols:
        num_proto = multiprotocols[host_name]['freq']
        protos = multiprotocols[host_name]['lists']
        if num_proto > 1:
            WARN(
                f'{" " * 5}⚠️  Host: {host_name} is running {num_proto} protocols {protos} recommended is 1'
            )
        elif num_proto == 1:
            GOOD(
                f'{" " * 5}✅ Host: {host_name} is running {num_proto} protocols {protos}')

    for host_name in protocol_host_names:
        if host_name in list(dict.fromkeys(multiprotocols)):
            continue
        GOOD(f'{" " * 5}✅ Host: {host_name} is running 0 protocols')


def client_web_test(results):
    new_results = (dict(results))
    for item in new_results.items():
        client_name = item[0]
        http_status_code = (item[1])
        if http_status_code == "200":
            GOOD(
                f'{" " * 5}✅ Client web connectivity check passed on host: {client_name}')
        else:
            WARN(
                f'{" " * 5}⚠️  Client web connectivity check failed on host: {client_name}')


def invalid_endpoints(host_name, result, backend_ips):
    result = result.replace(', ]}]', ']}]').replace('container', '"container"').replace(
        'ip', '"ip"').replace(' {', ' "').replace('},', '",')
    result = result.split('\n')[:]

    def ip_by_containers(result):
        INFO2("{}Validating endpoint-ips on host {}:".format(" " * 2, host_name))
        for line in result:
            endpoint_data = json.loads(line)
            bad_backend_ip = []
            for container, ips in endpoint_data:
                container = endpoint_data[0]['container']
                ips = endpoint_data[0]['ip']
                for ip in ips:
                    if ip not in backend_ips or ip == '0.0.0.0':
                        bad_backend_ip += [ip]

                if bad_backend_ip == []:
                    GOOD(
                        f'{" " * 5}✅ No invalid endpoint ips found on host: {host_name} container: {container}')
                else:
                    WARN(
                        f'{" " * 5}⚠️  Invalid endpoint ips found on host: {host_name} container: {container} invalid ips: {bad_backend_ip}')

    ip_by_containers(result)


def data_dir_check(host_name, result):
    directory_by_host = {host_name: []}
    for line in result.splitlines():
        usage = int(line.split('\t')[0])
        directory = line.split('\t')[1].split('/')[4]
        item_list = ([directory, usage])
        directory_by_host[host_name].append(item_list)

    for key, value in directory_by_host.items():
        INFO2(f'{" " * 2}Checking weka container status on host {key}:')
        for sublist in value:
            dir = sublist[0]
            use = sublist[1]
            if use < 10000:
                GOOD(f'{" " * 5}✅ Data directory {dir} acceptable size {use} MB')
            else:
                WARN(
                    f'{" " * 5}⚠️  Data directory {dir} larger than acceptable size {use} MB')


def parallel_execution(hosts, commands, use_check_output=True, use_json=False, use_call=False, ssh_identity=None):
    results = []
    spinner = Spinner('  Retrieving Data  ', color=colors.OKCYAN)
    spinner.start()

    SSH_OPTIONS = [['-o', 'PasswordAuthentication=no'], ['-o', 'LogLevel=ERROR'], ['-o',
                    'UserKnownHostsFile=/dev/null'], ['-o', 'StrictHostKeyChecking=no'], ['-o', 'ConnectTimeout=10']]

    ssh_opts = SSH_OPTIONS

    if ssh_identity:
        ssh_opts += [['-i', ssh_identity]]

    def run_command(host, command, use_check_output, use_json, use_call, ssh_opts):
        if isinstance(host, dict):
            host_ip = host['ip']
            host_name = host['name']
        else:
            host_ip = host
            host_name = host

        ssh_opts_flat = list(itertools.chain(*ssh_opts))

        if use_check_output:
            result = subprocess.check_output(
                ['ssh'] + ssh_opts_flat + [host_ip, command]).decode('utf-8').strip()
        elif use_json:
            result = json.loads(subprocess.check_output(
                ['ssh'] + ssh_opts_flat + [host_ip, command]).decode('utf-8').strip())
        elif use_call:
            result = subprocess.call(['ssh'] + ssh_opts_flat + [host_ip, command],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        else:
            result = subprocess.run(['ssh'] + ssh_opts_flat + [host_ip, command],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return host_name, result

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        future_to_host = {executor.submit(run_command, host, command, use_check_output,
                                          use_json, use_call, ssh_opts): host for host in hosts for command in commands}
        for future in concurrent.futures.as_completed(future_to_host):
            host = future_to_host[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                host_name = host['name'] if isinstance(host, dict) else host
                WARN(f'{" " * 5}⚠️  Unable to determine Host: {host_name} results')

    spinner.stop()
    return results


# backend checks
def backend_host_checks(backend_hosts, ssh_bk_hosts, weka_version, check_version, backend_ips, ssh_identity):
    INFO("CHECKING PASSWORDLESS SSH CONNECTIVITY")
    results = parallel_execution(
        ssh_bk_hosts, ['/bin/true'], use_check_output=False, use_call=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            ssh_bk_hosts = ssh_check(
                host_name, result, ssh_bk_hosts)
        else:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")

    if len(ssh_bk_hosts) == 0:
        BAD(f'{" " * 5}❌ Unable to proceed, Password SSH not configured on any host')
        sys.exit(1)

    if V(weka_version) >= V("3.12"):
        INFO("CHECKING IF OS IS SUPPORTED ON BACKENDS")
        results = parallel_execution(ssh_bk_hosts, [
            'OS=$(sudo cat /etc/os-release | awk -F= "/^ID=/ {print $2}" > /dev/null); if [[ $OS == "centos" ]]; then sudo cat /etc/centos-release; else sudo cat /etc/os-release; fi'], use_check_output=True, ssh_identity=ssh_identity)
        for host_name, result in results:
            if result is not None:
                check_os_release(host_name, result, weka_version,
                                 check_version, backend=True)
            else:
                WARN(f"Unable to determine Host: {host_name} OS version")

    INFO("CHECKING WEKA AGENT STATUS ON BACKENDS")
    results = parallel_execution(ssh_bk_hosts, [
        'sudo service weka-agent status'], use_check_output=False, use_call=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            weka_agent_check(host_name, result)
        else:
            WARN(f"Unable to determine Host: {host_name} weka-agent status")

    INFO("CHECKING TIME DIFFERENCE ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts, ['date --utc +%s'], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            time_check(host_name, result)
        else:
            WARN(f"Unable to determine time on Host: {host_name}")

    INFO("CHECKING WEKA DATA DIRECTORY SPACE USAGE ON BACKENDS")
    data_dir = os.path.join(f'/opt/weka/data/*_{str(weka_version)}')
    results = parallel_execution(ssh_bk_hosts, [
                                "df -m /opt/weka | awk 'NR==2 {print $4}'", "sudo du -smc %s" "| awk '/total/ {print $1}'" % (data_dir)], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine Host: {host_name} available space")

    free_space_check_data(host_name, results)


    INFO("CHECKING WEKA LOGS DIRECTORY SPACE USAGE ON BACKENDS")
    results = parallel_execution(ssh_bk_hosts, [
        "df -m /opt/weka/logs/ | awk 'NR==2 {print $3, $4}'"], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine Host: {host_name} available space")

    free_space_check_logs(results)

    INFO("CHECKING BACKEND WEKA CONTAINER STATUS ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts, ['weka local ps -J'], use_check_output=False, use_json=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is None:
            WARN(
                f"Unable to determine Host: {host_name} weka container status")

    if results != []:
        weka_container_status(results, weka_version)

    INFO("CHECKING FOR WEKA MOUNTS ON BACKENDS")
    results = parallel_execution(ssh_bk_hosts, [
        "sudo mount -t wekafs | awk '{print $1, $2, $3}'"], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")

    weka_mounts(results)

    INFO("CHECKING IF WEKA FRONTEND IN USE")
    results = parallel_execution(
        ssh_bk_hosts, ['find /sys/class/bdi -name "wekafs*" | wc -l'], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            frontend_check(host_name, result)
        else:
            WARN(f"Unable to determine frontend status on Host: {host_name}")

    INFO("CHECKING NUMBER OF RUNNING PROTOCOLS ON BACKENDS")
    protocol_host(backend_hosts)

    INFO("CHECKING FOR INVALID ENDPOINT IPS ON BACKENDS")
    results = parallel_execution(ssh_bk_hosts, [
        "container_name=$(weka local ps --no-header -o name| egrep -v 'samba|s3|ganesha|envoy'); for name in $container_name; do echo -en [{container: {$name}, ip: [; sudo weka local resources --stable --container $name -J | grep -w ip | awk '{print $2}' | tr '\n' ' '; echo -e ]}]; done"], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")
        else:
            invalid_endpoints(host_name, result, backend_ips)

    INFO("CHECKING WEKA DATA DIRECTORY SIZE ON BACKENDS")
    data_dir = os.path.join('/opt/weka/data/')
    results = parallel_execution(
        ssh_bk_hosts,
        [
            f'for name in $(weka local ps --no-header -o name,versionName| egrep -v "samba|smbw|s3|ganesha|envoy" | tr -s " " "_"); do du -sm {data_dir}"$name"; done'
        ],
        use_check_output=True, ssh_identity=ssh_identity
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")
        else:
            data_dir_check(host_name, result)


# CLIENT CHECKES
def client_hosts_checks(weka_version, ssh_cl_hosts, check_version, ssh_identity):
    INFO("CHECKING PASSWORDLESS SSH CONNECTIVITY ON CLIENTS")
    ssh_cl_hosts_dict = [{'name': host} for host in ssh_cl_hosts]
    results = parallel_execution(
        ssh_cl_hosts, ['/bin/true'], use_check_output=False, use_call=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            ssh_cl_hosts_dict = ssh_check(
                host_name, result, ssh_cl_hosts_dict)
        else:
            WARN(f'{" " * 5}⚠️  Unable to determine weka mounts on Host: {host_name}')

    ssh_cl_hosts = [host_dict['name'] for host_dict in ssh_cl_hosts_dict]
    if len(ssh_cl_hosts) == 0:
        BAD(f'{" " * 5}❌ Unable to proceed, Password SSH not configured on any host')
        sys.exit(1)

    if V(weka_version) >= V("3.12"):
        INFO("CHECKING IF OS IS SUPPORTED ON CLIENTS")
        results = parallel_execution(ssh_cl_hosts, [
            'OS=$(sudo cat /etc/os-release | awk -F= "/^ID=/ {print $2}" > /dev/null); if [[ $OS == "centos" ]]; then sudo cat /etc/centos-release; else sudo cat /etc/os-release; fi'], use_check_output=True)
        for host_name, result in results:
            if result is not None:
                check_os_release(host_name, result, weka_version,
                                 check_version, backend=False, client=True)
            else:
                WARN(f"Unable to determine Host: {host_name} OS version")

    INFO("CLIENT WEB CONNECTIVITY TEST ON CLIENTS")
    if len(ssh_cl_hosts) != 0:
        results = parallel_execution(ssh_cl_hosts, [
            'curl -sL -w "%{http_code}" "http://get.weka.io" -o /dev/null'], use_check_output=True, ssh_identity=ssh_identity)
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to determine weka mounts on Host: {host_name}")

        client_web_test(results)
    else:
        GOOD(f'{" " * 5}✅ Skipping clients check, no online clients found')

    INFO("CHECKING TIME DIFFERENCE ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts, ['date --utc +%s'], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            time_check(host_name, result)
        else:
            WARN(f"Unable to determine Host: {host_name} weka-agent status")

    INFO("CHECKING WEKA MOUNT POINTS ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts, ['sudo mountpoint -qd /weka/ | wc -l'], use_check_output=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            client_mount_check(host_name, result)
        else:
            WARN(f"Unable to determine wekafs mounts on client: {host_name}")

    INFO("CHECKING WEKA AGENT STATUS ON CLIENTS")
    results = parallel_execution(ssh_cl_hosts, [
        'sudo service weka-agent status'], use_check_output=False, use_call=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is not None:
            weka_agent_check(host_name, result)
        else:
            WARN(f"Unable to determine time on Host: {host_name}")

    INFO("CHECKING WEKA CONTAINER STATUS ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts, ['weka local ps -J'], use_check_output=False, use_json=True, ssh_identity=ssh_identity)
    for host_name, result in results:
        if result is None:
            WARN(
                f"Unable to determine Host: {host_name} weka container status")

    if results != []:
        weka_container_status(results, weka_version)


create_tar_file(log_file_path, "./weka_upgrade_checker.tar.gz")


def main():
    parser = argparse.ArgumentParser(description='Weka Upgrade Checker')

    parser.add_argument('-b', '--check-specific-backend-hosts', dest='check_specific_backend_hosts',
                        default=False, nargs='+', help='Provide one or more ips or fqdn of hosts to check, seperated by space')
    parser.add_argument('-c', '--skip-client-checks', dest='skip_client_checks',
                        action='store_true', default=True, help='Skipping all client checks')
    parser.add_argument('-a', '--run-all-checks', dest='run_all_checks', action='store_true',
                        default=False, help='Run check on entire cluster including backend hosts and client hosts')
    parser.add_argument('-i', '--ssh_identity', default=None,
                        type=str, help='Path to identity file for SSH')
    parser.add_argument('-v', '--version', dest='version', action='store_true',
                        default=False, help='weka_upgrade_check.py version info')

    args = parser.parse_args()

    ssh_identity = args.ssh_identity or None

    if args.run_all_checks:
        weka_cluster_results = weka_cluster_checks()
        backend_hosts = weka_cluster_results[0]
        ssh_bk_hosts = weka_cluster_results[1]
        client_hosts = weka_cluster_results[2]
        ssh_cl_hosts = weka_cluster_results[3]
        weka_info = weka_cluster_results[4]
        weka_version = weka_info['release']
        check_version = weka_cluster_results[5]
        backend_ips = weka_cluster_results[6]
        backend_host_checks(backend_hosts, ssh_bk_hosts,
                            weka_version, check_version, backend_ips, ssh_identity)
        client_hosts_checks(weka_version, ssh_cl_hosts,
                            check_version, ssh_identity)
        INFO(f"Cluster upgrade checks complete!")
        sys.exit(0)
    elif args.check_specific_backend_hosts:
        weka_cluster_results = weka_cluster_checks()
        backend_hosts = weka_cluster_results[0]
        ssh_bk_hosts = weka_cluster_results[1]
        client_hosts = weka_cluster_results[2]
        ssh_cl_hosts = weka_cluster_results[3]
        weka_info = weka_cluster_results[4]
        weka_version = weka_info['release']
        check_version = weka_cluster_results[5]
        backend_ips = weka_cluster_results[6]
        backend_host_checks(backend_hosts, args.check_specific_backend_hosts,
                            weka_version, check_version, backend_ips, ssh_identity)
        INFO(f"Cluster upgrade checks complete!")
        sys.exit(0)
    elif args.skip_client_checks:
        weka_cluster_results = weka_cluster_checks()
        backend_hosts = weka_cluster_results[0]
        ssh_bk_hosts = weka_cluster_results[1]
        client_hosts = weka_cluster_results[2]
        ssh_cl_hosts = weka_cluster_results[3]
        weka_info = weka_cluster_results[4]
        weka_version = weka_info['release']
        check_version = weka_cluster_results[5]
        backend_ips = weka_cluster_results[6]
        backend_host_checks(backend_hosts, ssh_bk_hosts,
                            weka_version, check_version, backend_ips, ssh_identity)
        INFO(f"Cluster upgrade checks complete!")
        sys.exit(0)
    elif args.version:
        print("Weka upgrade checker version: %s" % pg_version)
        sys.exit(0)


if __name__ == '__main__':
    main()
