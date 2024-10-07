#!/usr/bin/env python3

import argparse
import concurrent.futures
import datetime
import itertools
import json
import logging
import os
import re
import subprocess
import sys
import tarfile
import threading
import time
from itertools import chain
from subprocess import run
import warnings
from collections import Counter, defaultdict

warnings.filterwarnings("ignore", category=DeprecationWarning, module="distutils")

if sys.version_info < (3, 7):
    print("Must have Python version 3.7 or later installed.")
    sys.exit(1)

# Install and import the necessary version module based on Python version
if sys.version_info >= (3, 10):
    try:
        import pkg_resources

        pkg_resources.get_distribution("packaging")
    except (pkg_resources.DistributionNotFound, ImportError):
        print("The 'packaging' module is not installed. Installing it now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "packaging"])
        from packaging.version import parse, InvalidVersion, Version as V
    else:
        from packaging.version import parse, InvalidVersion, Version as V
else:
    # For Python versions 3.7 up to 3.9, use distutils
    from distutils.version import LooseVersion as V

    parse = V

pg_version = "1.3.44"

log_file_path = os.path.abspath("./weka_upgrade_checker.log")

logging.basicConfig(
    handlers=[logging.FileHandler(filename=log_file_path, encoding="utf-8", mode="w")],
    format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
    datefmt="%F %A %T",
    level=logging.DEBUG,
)

if sys.stdout.encoding != "UTF-8":
    if sys.version_info >= (3, 7):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore
    else:
        # This block is for Python 3.6
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
        sys.stdin = open(sys.stdin.fileno(), mode="r", encoding="utf-8", buffering=1)

try:
    "❌  ✅".encode(sys.stdout.encoding)
    unicode_test = True
except UnicodeEncodeError:
    unicode_test = False


if not unicode_test:
    [FAIL] = "\u274C"
    [PASS] = "\u2705"
    [WARN] = "\u26A0"
    [BAD] = "\u274C"

logger = logging.getLogger(__name__)


class colors:
    HEADER = "\033[95m"
    OKPURPLE = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


num_warn = 0
num_bad = 0
num_good = 0


def INFO(text):
    nl = "\n"
    print(f"{colors.OKPURPLE}{nl}{text}{nl}{colors.ENDC}")
    logging.info(text)


def INFO2(text):
    nl = "\n"
    print(f"{colors.OKCYAN}{nl}{text}{nl}{colors.ENDC}")
    logging.info(text)


def GOOD(text):
    global num_good
    print(f"{colors.OKGREEN}{text}{colors.ENDC}")
    logging.info(text)
    num_good += 1


def GOOD2(text):
    global num_good
    print(f"{colors.OKGREEN}✅  {text}{colors.ENDC}")
    logging.info(text)
    num_good += 1


def WARN(text):
    global num_warn
    print(f"{colors.WARNING}{text}{colors.ENDC}")
    logging.warning(text)
    num_warn += 1


def BAD(text):
    global num_bad
    print(f"{colors.FAIL}{text}{colors.ENDC}")
    logging.debug(text)
    num_bad += 1


class Host:
    def __init__(self, host_json):
        self.typed_id = str(host_json["host_id"])
        self.id = re.search("HostId<(\\d+)>", self.typed_id)[1]  # type: ignore
        self.ip = str(host_json["host_ip"])
        self.port = str(host_json["mgmt_port"])
        self.hostname = str(host_json["hostname"])
        self.mode = str(host_json["mode"])
        self.is_up = host_json["status"]
        self.state = host_json["state"]
        self.sw_version = host_json["sw_version"]
        self.container = host_json["container_name"]
        self.cores = host_json["cores"]
        self.cores_ids = host_json["cores_ids"]
        self.memory = host_json["memory"]
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
        self.aws_zone = (
            str(host_json["aws"]["availability_zone"])
            if "availability_zone" in host_json
            else None
        )
        self.aws_id = (
            str(host_json["aws"]["instance_id"]) if "instance_id" in host_json else None
        )
        self.aws_type = (
            str(host_json["aws"]["instance_type"])
            if "instance_type" in host_json
            else None
        )


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
                self.spinner_index = (self.spinner_index + 1) % self.spinner_length
                time.sleep(0.1)

        self.spinner_thread = threading.Thread(target=spin)
        self.spinner_thread.start()

    def stop(self):
        self.running = False
        self.spinner_thread.join()
        sys.stdout.write(
            "\r" + " " * (len(self.message) + len(self.spinner_chars) + 2) + "\r"
        )
        sys.stdout.flush()


def printlist(lst, num):
    global num_warn
    for i in range(0, len(lst), num):
        if num == 6:
            WARN("⚠️  {} {} {} {} {} {}".format(*lst[i : i + num]))
            logging.warning("⚠️  {} {} {} {} {} {}".format(*lst[i : i + num]))
            num_warn += 1
        elif num == 5:
            WARN("⚠️  {} {} {} {} {}".format(*lst[i : i + num]))
            logging.warning("⚠️  {} {} {} {} {}".format(*lst[i : i + num]))
            num_warn += 1
        elif num == 4:
            WARN("⚠️  {} {} {} {}".format(*lst[i : i + num]))
            logging.warning("⚠️  {} {} {} {}".format(*lst[i : i + num]))
            num_warn += 1
        elif num == 3:
            WARN("⚠️  {} {} {}".format(*lst[i : i + num]))
            logging.warning("⚠️  {} {} {}".format(*lst[i : i + num]))
            num_warn += 1
        elif num == 2:
            WARN("⚠️  {} {}".format(*lst[i : i + num]))
            logging.warning("⚠️  {} {}".format(*lst[i : i + num]))
            num_warn += 1
        elif num == 1:
            WARN("⚠️  {}".format(*lst[i : i + num]))
            logging.warning("⚠️  {}".format(*lst[i : i + num]))
            num_warn += 1


def create_tar_file(source_file, output_path):
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    tar_file_name = f"{os.path.splitext(source_file)[0]}_{timestamp}.tar.gz"
    with tarfile.open(tar_file_name, "w:gz") as tar:
        tar.add(source_file)


def get_online_version():
    git_file_url = "https://raw.githubusercontent.com/weka/tools/master/weka_upgrade_checker/weka_upgrade_checker.py"
    curl_command = f"curl -s --connect-timeout 5 {git_file_url}"

    try:
        file_content = subprocess.check_output(
            curl_command, shell=True, universal_newlines=True
        )
        search_version = "pg_version ="
        lines = file_content.splitlines()
        found_version = []
        for line in lines:
            if search_version in line and "=" in line:
                online_version = line.split("=")[1].strip('" "')
                found_version.append(online_version)

        if found_version:
            return found_version[0]
        else:
            return None
    except subprocess.CalledProcessError:
        return None


def check_version():
    INFO("VERIFYING IF RUNNING LATEST VERSION OF WEKA UPGRADE CHECKER")
    online_version = get_online_version()

    if online_version:
        if V(pg_version) < V(online_version):
            BAD(
                f"❌  You are not running the latest version of weka upgrade checker current version {pg_version} latest version {online_version}"
            )
        else:
            GOOD(f"✅  Running the latest version of weka upgrade checker {pg_version}")
    else:
        try:
            with open("version.txt", "r") as file:
                latest_version = file.read().strip("\n")
                if V(pg_version) < V(latest_version):
                    BAD(
                        f"❌  You are not running the latest version of weka upgrade checker current version {pg_version} latest version {latest_version}"
                    )
                else:
                    GOOD(
                        f"✅  Running the latest version of weka upgrade checker {pg_version}"
                    )
        except FileNotFoundError:
            BAD("❌  Unable to check the latest version of weka upgrade checker.")


check_version()


def weka_cluster_checks(skip_mtu_check):
    INFO("VERIFYING WEKA AGENT STATUS")
    weka_agent_service = subprocess.call(
        ["sudo", "service", "weka-agent", "status"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    if weka_agent_service != 0:
        BAD(
            "❌  Weka is NOT installed on host or the container is down, cannot continue"
        )
        sys.exit(1)
    else:
        GOOD("✅  Weka agent service is running")

    INFO("VERIFYING WEKA LOCAL CONTAINER STATUS")
    running_container = []
    con_status = json.loads(subprocess.check_output(["weka", "local", "status", "-J"]))
    for container in con_status:
        if (
            con_status[container]["type"] == "weka"
            and con_status[container]["isRunning"]
        ):
            GOOD("✅  Weka local container is running")
            running_container += [container]
            break
    else:
        BAD("❌  Weka local container is NOT running, cannot continue")
        sys.exit(1)

    INFO("WEKA USER LOGIN TEST")
    p = run(["weka", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        BAD("❌  Please login using weka user login first, cannot continue")
        sys.exit(1)
    else:
        GOOD("✅  Weka user login successful")

    INFO("WEKA IDENTIFIED")
    weka_info = json.loads(subprocess.check_output(["weka", "status", "-J"]))
    cluster_name = weka_info["name"]
    weka_status = weka_info["status"]
    uuid = weka_info["guid"]
    weka_version = weka_info["release"]
    usable_capacity = weka_info["capacity"]["total_bytes"]
    weka_buckets = weka_info["buckets"]["total"]

    GOOD(
        f"✅  CLUSTER:{cluster_name} STATUS:{weka_status} VERSION:{weka_version} UUID:{uuid}"
    )

    if any(c.isalpha() for c in weka_version) and not weka_version.endswith("-hcfs"):
        INFO("CHECKING WEKA HOTFIX VERSION")
        WARN(
            f"⚠️  The cluster maybe running a specialized hotfix version of Weka {weka_version}; confirm that required hotfixes are included in upgrade target version."
        )

    class Machine:
        def __init__(self, machine_json):
            self.name = str(machine_json["name"])
            self.ip = str(machine_json["primary_ip_address"])
            self.port = str(machine_json["primary_port"])
            self.roles = str(machine_json["roles"])
            self.is_up = machine_json["status"]
            self.uid = str(machine_json["uid"])
            self.versions = machine_json["versions"][0]
            if V(weka_version) > V("4.1"):
                self.containers = machine_json["hosts"]["map"]

    INFO("CHECKING FOR WEKA ALERTS")
    weka_alerts = (
        subprocess.check_output(["weka", "alerts", "--no-header"])
        .decode("utf-8")
        .rstrip("\n")
        .split("\n")
    )
    if len(weka_alerts) == 0:
        GOOD("✅  No Weka alerts present")
    else:
        WARN(f"⚠️  {len(weka_alerts)} Weka alerts present")
        for alert in weka_alerts:
            logging.warning(alert)

    INFO("VERIFYING CUSTOM SSL CERT")
    try:
        file_path = f"/opt/weka/dist/release/{weka_version}.spec"
        with open(file_path, "r") as file:
            content = file.read()
            if "SSL_CERT_FILE" in content:
                BAD(
                    "❌  Custom ssl certificate detected, please contact Weka Support before upgrading"
                )
            else:
                GOOD("✅  No custom ssl certificate found")
    except FileNotFoundError:
        BAD("❌  Unable to determine if custom ssl certificate is installed.")

    INFO("CHECKING REBUILD STATUS")
    rebuild_status = json.loads(
        subprocess.check_output(["weka", "status", "rebuild", "-J"])
    )
    if rebuild_status["progressPercent"] == 0:
        GOOD("✅  No rebuild in progress")
    else:
        WARN(f'⚠️  Rebuild in progress {rebuild_status["progressPercent"]} complete')

    if V("4.0.5.39") <= V(weka_version) < V("4.1"):
        INFO("VERIFYING WEKA BACKEND MACHINES")
        weka_bk_machines = [
            Machine(machine_json)
            for machine_json in json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "machines", "list", "--role", "backend", "-J"]
                )
            )
        ]
        backend_hosts = [
            Host(host_json)
            for host_json in json.loads(
                subprocess.check_output(["weka", "cluster", "host", "-b", "-J"])
            )
        ]
        ssh_bk_hosts = [
            {"name": w_bk_machine.name, "ip": w_bk_machine.ip}
            for w_bk_machine in weka_bk_machines
            if w_bk_machine.is_up != "DOWN"
        ]
        down_bk_machine = []
        for w_bk_machine in weka_bk_machines:
            if w_bk_machine.is_up != "UP":
                down_bk_machine += [
                    w_bk_machine.name,
                    w_bk_machine.ip,
                    w_bk_machine.is_up,
                ]

        if not down_bk_machine:
            GOOD("✅  No failed hosts detected")
        else:
            WARN(f"Unhealthy backend hosts detected\n")
            printlist(down_bk_machine, 3)

    elif V(weka_version) >= V("4.1"):
        INFO("VERIFYING WEKA BACKEND MACHINES")
        weka_bk_servers = [
            Machine(machine_json)
            for machine_json in json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "servers", "list", "--role", "backend", "-J"]
                )
            )
        ]
        backend_hosts = [
            Host(host_json)
            for host_json in json.loads(
                subprocess.check_output(["weka", "cluster", "container", "-b", "-J"])
            )
        ]
        ssh_bk_hosts = [
            {"name": w_bk_server.name, "ip": w_bk_server.ip}
            for w_bk_server in weka_bk_servers
            if w_bk_server.is_up != "DOWN"
        ]
        down_bk_servers = []
        for w_bk_server in weka_bk_servers:
            if w_bk_server.is_up != "UP":
                down_bk_servers += [w_bk_server.name, w_bk_server.ip, w_bk_server.is_up]

        if not down_bk_servers:
            GOOD("✅  No failed hosts detected")
        else:
            WARN(f"Unhealthy backend hosts detected\n")
            printlist(down_bk_servers, 3)
    else:
        INFO("VERIFYING WEKA BACKEND HOST STATUS")
        backend_hosts = [
            Host(host_json)
            for host_json in json.loads(
                subprocess.check_output(["weka", "cluster", "host", "-b", "-J"])
            )
        ]
        ssh_bk_hosts = [
            {"name": bkhost.hostname, "ip": bkhost.ip}
            for bkhost in backend_hosts
            if bkhost.is_up != "DOWN"
        ]
        down_bkhost = []
        for bkhost in backend_hosts:
            if bkhost.is_up != "UP":
                down_bkhost += [
                    bkhost.typed_id,
                    bkhost.hostname,
                    bkhost.ip,
                    bkhost.sw_version,
                    bkhost.mode,
                ]

        if not down_bkhost:
            GOOD("✅  No failed hosts detected")
        else:
            WARN(f"Unhealthy backend hosts detected\n")
            printlist(down_bkhost, 5)

    if V("4.0.6") <= V(weka_version) < V("4.1"):
        INFO("VERIFYING WEKA CLIENT MACHINES")
        weka_cl_machines = [
            Machine(machine_json)
            for machine_json in json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "machines", "list", "--role", "client", "-J"]
                )
            )
        ]
        client_hosts = [
            Host(host_json)
            for host_json in json.loads(
                subprocess.check_output(["weka", "cluster", "host", "-c", "-J"])
            )
        ]
        ssh_cl_hosts = [
            {"name": w_cl_machine.name, "ip": w_cl_machine.ip}
            for w_cl_machine in weka_cl_machines
            if w_cl_machine.is_up
        ]
        down_cl_machine = []
        for w_cl_machine in weka_cl_machines:
            if w_cl_machine.is_up != "UP":
                down_cl_machine += (
                    w_cl_machine.name,
                    w_cl_machine.ip,
                    w_cl_machine.is_up,
                )

        if not down_cl_machine:
            GOOD("✅  No failed clients detected")
        else:
            WARN(f"Failed clients detected\n")
            printlist(down_cl_machine, 3)

    elif V(weka_version) >= V("4.1"):
        INFO("VERIFYING WEKA CLIENT MACHINES")
        weka_cl_servers = [
            Machine(machine_json)
            for machine_json in json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "servers", "list", "--role", "client", "-J"]
                )
            )
        ]
        client_hosts = [
            Host(host_json)
            for host_json in json.loads(
                subprocess.check_output(["weka", "cluster", "container", "-c", "-J"])
            )
        ]
        ssh_cl_hosts = [
            {"name": w_cl_server.name, "ip": w_cl_server.ip}
            for w_cl_server in weka_cl_servers
            if w_cl_server.is_up
        ]
        down_cl_servers = []
        for w_cl_server in weka_cl_servers:
            if not w_cl_server.is_up:
                down_cl_servers += [w_cl_server.name, w_cl_server.ip, w_cl_server.is_up]

        if not down_cl_servers:
            GOOD("✅  No failed hosts detected")
        else:
            WARN(f"Unhealthy backend hosts detected\n")
            printlist(down_cl_servers, 3)

    else:
        INFO("VERIFYING WEKA CLIENT MACHINES")
        client_hosts = [
            Host(host_json)
            for host_json in json.loads(
                subprocess.check_output(["weka", "cluster", "host", "-c", "-J"])
            )
        ]

        ssh_cl_hosts = [
            {"name": cl_host.hostname, "ip": cl_host.ip}
            for cl_host in client_hosts
            if cl_host.is_up != "DOWN"
        ]

        down_clhost = []
        for client in client_hosts:
            if client.is_up != "UP":
                down_clhost += [
                    client.typed_id,
                    client.hostname,
                    client.ip[0],
                    client.is_up,
                    client.mode,
                ]

        if not down_clhost:
            GOOD("✅  No failed clients detected")
        else:
            WARN(f"Failed clients detected\n")
            printlist(down_clhost, 5)

    if V(weka_version) >= V("4.0"):
        INFO("Validating all containers on the same source version")
        weka_version_current = (
            subprocess.check_output(["weka", "version", "current"]).decode().strip()
        )

        def extract_main_version(version):
            if isinstance(version, str) and version:  # Check if it's a non-empty string
                match = re.match(r"(\d+\.\d+)", version)
                return match.group(1) if match else version
            else:
                WARN(f"Unable to determine sw_release_string: {version}")
                return None

        weka_main_version_current = extract_main_version(weka_version_current)

        if all(
            extract_main_version(host.sw_release_string) == weka_main_version_current
            for host in backend_hosts
        ):
            GOOD("✅  All containers are on the same source version")
        else:
            WARN(
                "⚠️  Containers running multiple source versions detected. Please contact WEKA customer success if upgrade is possible ref WEKAPP-434837"
            )
    if V(weka_version) >= V("4.0"):
        INFO("Validating compute containers are on same version")
        compute_release = []
        for host in backend_hosts:
            if host.container.startswith("compute"):
                compute_release.append(host.sw_release_string)

        if all(version == compute_release[0] for version in compute_release):
            GOOD("✅  All compute containers are on the same WEKA version")
        else:
            BAD(
                "❌  Multiple version detected for compute containers. All compute containers should be on the same version before upgrading"
            )

    INFO("Validating compute processes avg CPU utilization")
    spinner = Spinner("  Processing Data   ", color=colors.OKCYAN)
    spinner.start()
    try:
        if V(weka_version) >= V("4.0"):
            compute_process_ids = json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "process", "-b", "-F", "role=COMPUTE", "-J"]
                )
            )
        else:
            compute_process_ids = json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "nodes", "-b", "-F", "role=COMPUTE", "-J"]
                )
            )
        node_ids = [item["node_id"] for item in compute_process_ids]
        just_node_ids = ",".join(
            [
                str(node_id).replace("NodeId<", "").replace(">", "")
                for node_id in node_ids
            ]
        )
        if V(weka_version) >= V("4.0"):
            percentage_str = (
                subprocess.check_output(
                    [
                        "weka",
                        "stats",
                        "--stat",
                        "CPU_UTILIZATION",
                        "--interval",
                        "21600",
                        "--resolution-secs",
                        "21600",
                        "--no-header",
                        "-o",
                        "value",
                        "--process-ids",
                        just_node_ids,
                    ]
                )
                .decode("utf-8")
                .strip()
            )
        else:
            percentage_str = (
                subprocess.check_output(
                    [
                        "weka",
                        "stats",
                        "--stat",
                        "CPU_UTILIZATION",
                        "--interval",
                        "21600",
                        "--resolution-secs",
                        "21600",
                        "--no-header",
                        "-o",
                        "value",
                        "--node-ids",
                        just_node_ids,
                    ]
                )
                .decode("utf-8")
                .strip()
            )
        percentage = float(percentage_str.replace("%", ""))
        if percentage >= 60:
            WARN(
                f"⚠️  Compute processes CPU utilization too high at {percentage}%, upgrade may cause performance impact"
            )
        else:
            GOOD("✅  Compute processes CPU utilization ok")
    except subprocess.CalledProcessError as e:
        WARN(f"⚠️  Error executing command: {e.output.decode('utf-8').strip()}")
    except ValueError as ve:
        WARN(f"⚠️  Error parsing CPU utilization value: {ve}")
    except Exception as ex:
        WARN(f"⚠️  Unexpected error: {str(ex)}")

    spinner.stop()

    host_to_process = {}

    def process_in_batches(host_to_process, max_parallel_executions=6):
        mtu_results = []
        batch_size = max_parallel_executions
        node_ids = list(host_to_process.values())
        for i in range(0, len(node_ids), batch_size):
            batch = node_ids[i : i + batch_size]
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=batch_size
            ) as executor:
                futures = [executor.submit(run_command, node_id) for node_id in batch]
                for future in concurrent.futures.as_completed(futures):
                    mtu_results.append(future.result())
            time.sleep(2)
        return mtu_results

    if not skip_mtu_check:
        INFO("Checking client side MTU mismatch")
        spinner = Spinner("  Processing Data   ", color=colors.OKCYAN)
        spinner.start()

        if V(weka_version) >= V("4.0"):
            drive_process_ids = json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "process", "-b", "-F", "role=DRIVES", "-J"]
                )
            )
        else:
            drive_process_ids = json.loads(
                subprocess.check_output(
                    ["weka", "cluster", "nodes", "-b", "-F", "role=DRIVES", "-J"]
                )
            )

        for id in drive_process_ids:
            process_id = id["node_id"]
            container_id = id["host_id"]
            if container_id not in host_to_process:
                host_to_process[container_id] = process_id

        for host_id, node_id in host_to_process.items():
            just_node_ids = str(node_id).replace("NodeId<", "").replace(">", "")
            host_to_process[host_id] = just_node_ids

        def run_command(node_id):
            try:
                command = [
                    "weka",
                    "debug",
                    "net",
                    "peers",
                    "--no-header",
                    node_id,
                    "--output",
                    "inMTU,outMTU",
                ]
                result = subprocess.check_output(command).decode("utf-8").strip()
                return f"Node {node_id}: {result}"
            except subprocess.CalledProcessError as e:
                return f"Node {node_id}: Error {str(e)}"

        mtu_results = process_in_batches(host_to_process, max_parallel_executions=2)

        mismatched_mtus = []

        for result in mtu_results:
            if "Node" in result:
                parts = result.split()
                node_id = parts[1].replace(":", "")
                inMTU = parts[2]
                outMTU = parts[3]
            else:
                parts = result.split()
                inMTU = parts[0]
                outMTU = parts[1]

            if inMTU != outMTU:
                mismatched_mtus.append(node_id)

        if mismatched_mtus != []:
            for node_id in mismatched_mtus:
                node_idx = f"NodeId<{node_id}>"
                for process in drive_process_ids:
                    if process["node_id"] == node_idx:
                        WARN(
                            f"⚠️  Asymmetric MTU detected for at least one peer of {process['nodeInfo']['hostname']}, ProcessId: {node_idx}"
                        )
        else:
            GOOD("✅  MTU check completed successfully")
    else:
        INFO("MTU mismatch check skipped.")

    spinner.stop()

    mtu_results = process_in_batches(host_to_process, max_parallel_executions=6)

    if V(weka_version) >= V("4.0"):
        INFO("Validating accepted versions list is empty")
        accepted_version = json.loads(
            subprocess.check_output(
                ["weka", "debug", "upgrade", "accepted-versions", "list"]
            )
        )

        if accepted_version and isinstance(accepted_version, list):
            WARN(
                "⚠️  Weka clients may have issues auto upgrading after rebooting current accepted version: "
                + ", ".join(accepted_version)
            )
        else:
            GOOD("✅  Accepted version list is empty")

    if V(weka_version) >= V("4.0"):
        INFO("Validating client target version")
        client_target_verion = (
            subprocess.check_output(
                ["weka", "cluster", "client-target-version", "show"]
            )
            .decode()
            .strip()
        )

        if client_target_verion != "":
            WARN(
                f"⚠️  Weka clients will remain on version: {client_target_verion} after upgrading"
            )
        else:
            GOOD("✅  Client target version is empty")

    if V(weka_version) >= V("4.0"):
        INFO("Validating memory to SSD capacity ratio for upgrade")
        total_compute_memory = sum(
            host.memory
            for host in backend_hosts
            if "compute" in host.container and host.is_up
        )
        ratio = usable_capacity / total_compute_memory
        if ratio > 2000:
            WARN(
                f"⚠️  The current ratio of {ratio} is below the recommended value, it is recommended to increase compute RAM"
            )
        else:
            GOOD("✅  Memory to SSD ratio validation ok")

    INFO("CHECKING CLIENT COMPATIBLE VERSIONS")
    try:
        sw_version = weka_version.split(".")
        check_version = ".".join(sw_version[:2])
        cl_machine_need_upgrade = []
        cl_host_need_upgrade = []
        if V("4.0") <= V(weka_version) < V("4.1"):
            try:
                for w_cl_machine in weka_cl_machines:
                    clsw_version = w_cl_machine.versions.split(".")
                    if ".".join(clsw_version[:2]) != check_version:
                        cl_machine_need_upgrade += [w_cl_machine.name, w_cl_machine.ip]
            except NameError as e:
                WARN("⚠️  Unable to determine client weka version")

        elif V(weka_version) >= V("4.1"):
            try:
                for w_cl_server in weka_cl_servers:
                    clsw_version = w_cl_server.versions.split(".")
                    if ".".join(clsw_version[:2]) != check_version:
                        cl_machine_need_upgrade += [w_cl_server.name, w_cl_server.ip]
            except NameError as e:
                WARN("⚠️  Unable to determine client weka version")
        else:
            try:
                for client in client_hosts:
                    clsw_version = client.sw_version.split(".")
                    if ".".join(clsw_version[:2]) != check_version:
                        cl_host_need_upgrade += [
                            client.typed_id,
                            client.hostname,
                            client.ip[0],
                            client.is_up,
                            client.mode,
                        ]
            except NameError as e:
                WARN("⚠️  Unable to determine client weka version")
    except NameError as e:
        WARN("⚠️  Unable to determine client weka version")

    if V(weka_version) >= V("4.0"):
        if cl_machine_need_upgrade:
            WARN(
                f"Following client hosts must be upgraded to {weka_version} prior to weka upgrade\n"
            )
            printlist(cl_machine_need_upgrade, 2)
        else:
            GOOD("✅  All clients hosts are up to date")
    elif not cl_host_need_upgrade:
        GOOD("✅  All clients hosts are up to date")
    else:
        WARN(
            f"Following client hosts must be upgraded to {weka_version} prior to weka upgrade\n"
        )
        printlist(cl_host_need_upgrade, 5)

    INFO("VERIFYING WEKA NODE STATUS")
    weka_nodes = json.loads(subprocess.check_output(["weka", "cluster", "nodes", "-J"]))
    down_node = []
    for node in weka_nodes:
        if node["status"] != "UP":
            down_node += [
                node["node_id"],
                node["hostname"],
                node["status"],
                node["mode"],
                node["roles"],
            ]

    if not down_node:
        GOOD("✅  No failed hosts detected")
    else:
        WARN(f"Failed nodes detected\n")
        printlist(down_node, 5)

    # need to check element names
    INFO("VERIFYING WEKA FS SNAPSHOTS UPLOAD STATUS")
    weka_snapshot = json.loads(
        subprocess.check_output(["weka", "fs", "snapshot", "-J"])
    )
    snap_upload = []
    for snapshot in weka_snapshot:
        if V(weka_version) < V("4.0.5"):
            if snapshot["stowStatus"] == "UPLOADING":
                snap_upload += [
                    snapshot["id"],
                    snapshot["filesystem"],
                    snapshot["name"],
                    snapshot["remote_object_status"],
                    snapshot["remote_object_progress"],
                ]
        else:
            if snapshot["remoteStowInfo"]["stowStatus"] == "UPLOADING":
                snap_upload += [
                    snapshot["snap_id"],
                    snapshot["filesystem"],
                    snapshot["name"],
                    snapshot["remoteStowInfo"]["stowStatus"],
                    snapshot["remoteStowInfo"]["stowProgress"],
                ]

    if not snap_upload:
        GOOD("✅  Weka snapshot upload status ok")
    else:
        WARN(f"Following snapshots are uploading\n")
        printlist(snap_upload, 5)

    if V("4.2.12") <= V(weka_version) <= V("4.3.5"):
        INFO("VERIFYING SNAPSHOT BUCKET COUNT")
        snap_layers = json.loads(
            subprocess.check_output(
                [
                    "weka",
                    "debug",
                    "config",
                    "show",
                    "snapLayers[*].stowInfo.LOCAL.bucketsNum",
                    "-J",
                ]
            )
        )
        unique_snap_layers = list(set(snap_layers))
        snap_result = any(x != weka_buckets and x != 0 for x in unique_snap_layers)
        if snap_result:
            BAD(
                "❌  Please contact WEKA Customer Success prior to upgrade, REF# WEKAPP-427366"
            )
        else:
            GOOD("✅  Snapshot bucket count complete")

    INFO("CHECKING FOR SMALL WEKA FILE SYSTEMS")
    wekafs = json.loads(subprocess.check_output(["weka", "fs", "-J"]))
    small_wekafs = []
    for fs in wekafs:
        if fs["available_total"] < 1073741824:
            small_wekafs += [
                fs["fs_id"],
                fs["group_name"],
                fs["name"],
                fs["status"],
                fs["available_total"],
            ]

    if not small_wekafs:
        GOOD("✅  No small Weka file system found")
    else:
        WARN(f"Found small file systems\n")
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
            "5.1-2.6.2.0",
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
            "5.6-2.0.9.0",
            "5.8-1.1.2.1",
        ],
        "3.14": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0",
            "5.8-1.1.2.1",
        ],
        "4.0": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0",
            "5.8-1.1.2.1",
        ],
        "4.1": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.4-3.5.8.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0",
            "5.7-1.0.2.0",
            "5.8-1.1.2.1",
        ],
        "4.2": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.4-3.5.8.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0",
            "5.7-1.0.2.0",
            "5.8-1.1.2.1",
            "5.9-0.5.6.0",
            "23.10-0.5.5.0",
            "23.10-1.1.9.0",
        ],
        "4.3": [
            "5.1-2.5.8.0",
            "5.1-2.6.2.0",
            "5.4-3.4.0.0",
            "5.4-3.5.8.0",
            "5.6-1.0.3.3",
            "5.6-2.0.9.0",
            "5.7-1.0.2.0",
            "5.8-1.1.2.1",
            "5.8-3.0.7.0",
            "5.9-0.5.6.0",
            "23.10-0.5.5",
            "23.04-1.1.3.0",
            "23.10-0.5.5.0",
        ],
    }

    # to handle non-standard PEP440 standard using parse
    INFO("VALIDATING BACKEND SUPPORTED NIC DRIVERS INSTALLED")
    spinner = Spinner("  Processing Data   ", color=colors.OKCYAN)
    spinner.start()

    backend_ips = [*{bkhost.ip for bkhost in backend_hosts}]
    backend_host_names = [*{bkhost.hostname for bkhost in backend_hosts}]
    hostname_from_api = []

    cmd = ["weka", "cluster", "host", "info-hw", "-J"]
    host_hw_info = json.loads(subprocess.check_output(cmd + backend_ips))

    ofed_downlevel = []
    current_version = {}

    def safe_parse(version_string):
        """Try parsing the version using packaging; fallback to LooseVersion."""
        try:
            # Try to parse with packaging's version parser (PEP 440 compliant)
            return parse(version_string)
        except InvalidVersion:
            try:
                cleaned_version = version_string.replace("-", ".")
                return V(cleaned_version)
            except Exception as e:
                print(f"Failed to parse version '{version_string}': {e}")
                return None

    for key, val in host_hw_info.items():
        if host_hw_info.get(key) is not None:
            try:
                if "Mellanox Technologies" not in (str(val["eths"])):
                    break
                key = [
                    *{bkhost.hostname for bkhost in backend_hosts if key == bkhost.ip}
                ][0]
                current_version[key] = []
                result = val["ofed"]["host"]
                current_version[key].append(result)
                hostname_from_api.append(key)

                result_parsed = safe_parse(result)
                threshold_parsed = safe_parse("5.1-2.5.8.0")

                if result_parsed < threshold_parsed:
                    ofed_downlevel.append((key, result))

                if result not in supported_ofed[check_version]:
                    BAD(
                        f'{" " * 5}❌  Host: {key} on weka version {weka_version} does not support OFED version {result}'
                    )
                else:
                    GOOD(
                        f'{" " * 5}✅  Host: {key} on weka version {weka_version} is running supported OFED version {result}'
                    )

            except Exception as e:
                print(f"Error processing host {key}: {e}")

    for bkhostnames in hostname_from_api:
        if bkhostnames in backend_host_names:
            backend_host_names.remove(bkhostnames)

    if not current_version:
        GOOD("✅  Mellanox nics not found")
    elif backend_host_names:
        for bkhostname in backend_host_names:
            WARN(f'{" " * 5}⚠️  Unable to determine Host: {bkhostname} OFED version')
    elif len(set(current_version)) == 1:
        WARN(f'\n{" " * 5}⚠️  Mismatch OFED version found on backend hosts\n')
        printlist(printlist, 1)

    spinner.stop()

    if V(weka_version) == V("3.12"):
        INFO("VERIFYING RAID REDUCTION SETTINGS")
        try:
            wekacfg = json.loads(
                subprocess.check_output(
                    [
                        "sudo",
                        "weka",
                        "local",
                        "run",
                        "--container",
                        running_container[0],
                        "--",
                        "/weka/cfgdump",
                    ]
                )
            )
            raid_reduction = wekacfg["clusterInfo"]["reserved"][1]
            if raid_reduction == 1:
                GOOD("✅  Raid Reduction is disabled")
            else:
                WARN(
                    '⚠️  Raid Reduction is ENABLED issue command "weka debug jrpc config_override_key '
                    + 'key="clusterInfo.reserved[1]" value=1" to disable'
                )
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN("⚠️  Unable able to determine Raid Reduction settings")

    if V(weka_version) == V("3.12"):
        INFO("VERIFYING TLS SECURITY SETTINGS")
        try:
            wekacfg = json.loads(
                subprocess.check_output(
                    [
                        "sudo",
                        "weka",
                        "local",
                        "run",
                        "--container",
                        running_container[0],
                        "--",
                        "/weka/cfgdump",
                    ]
                )
            )
            tls_security = wekacfg["clusterInfo"]["reserved"][1]
            if tls_security == 1:
                GOOD(f"✅  Raid Reduction is disabled")
            else:
                WARN(
                    '⚠️  Raid Reduction is ENABLED issue command "weka debug jrpc config_override_key '
                    + 'key="clusterInfo.reserved[1]" value=1" to disable'
                )
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN(f"⚠️  Unable able to determine Raid Reduction settings")

    if V("3.13") <= V(weka_version) < V("3.14"):
        INFO("VERIFYING UPGRADE ELIGIBILITY")
        link_type = weka_info["net"]["link_layer"]
        if link_type != "ETH":
            WARN(f"⚠️  Must upgrade to 3.14.3.16")
        elif ofed_downlevel:
            WARN(
                f"Upgrading to 3.14 requires Minimum OFED 5.1-2.5.8.0, following hosts need ofed updating\n"
            )
            printlist(ofed_downlevel, 2)
        else:
            GOOD(f"✅  Upgrade eligibility to Weka version 3.14+ verified")

    if V("3.14") == V(weka_version) < V("3.14.2"):
        INFO("VERIFYING UPGRADE ELIGIBILITY")
        if link_type != "ETH":
            BAD(
                "❌  Upgrading to 4.0 NOT supported. Requires Weka to use Ethernet connectivity and minimum "
                + "Weka version 3.14.1 or greater"
            )
        else:
            GOOD("✅  Cluster is upgrade eligible")

    if V(weka_version) == V("3.14"):
        weka_drives = json.loads(
            subprocess.check_output(["weka", "cluster", "drive", "-J"])
        )
        if "KIOXIA" in weka_drives:
            WARN(
                "⚠️  Contact Weka Support prior to upgrading to Weka 4.0, System identified with Kioxia drives"
            )
        else:
            GOOD("✅  No problematic drives found")

    if V(weka_version) == V("4.1.0.77"):
        INFO("VERIFYING SSD SUPPORTED SIZE")
        unsupported_drive = []
        weka_drives = json.loads(
            subprocess.check_output(["weka", "cluster", "drive", "-J"])
        )
        for drive in weka_drives:
            if drive["size_bytes"] >= 30725970923520:
                unsupported_drive += [
                    drive["disk_id"],
                    drive["node_id"],
                    drive["status"],
                    drive["size_bytes"],
                    drive["hostname"],
                ]

        if not unsupported_drive:
            GOOD("✅  SSD Drive check complete")
        else:
            WARN(
                "⚠️  Found unsupport SSD drive size. Please contact WEKA Support prior to upgrading"
            )
            printlist(unsupported_drive, 5)

    if V(weka_version) == V("3.14"):
        INFO("VERIFYING SYSTEM OPTIMAL SETTINGS")
        WARN(
            '⚠️  After upgrading to Weka 4.0.2, issue the following override command. "weka debug config '
            + 'override clusterInfo.allowDietAggressively false"'
        )

    if V("4") <= V(weka_version) < V("4.04"):
        INFO("VERIFYING RAID REDUCTION SETTINGS")
        try:
            wekacfg = json.loads(
                subprocess.check_output(
                    [
                        "sudo",
                        "weka",
                        "local",
                        "run",
                        "--container",
                        running_container[0],
                        "--",
                        "/weka/cfgdump",
                    ]
                )
            )
            raid_reduction = wekacfg["clusterInfo"]["allowDietAggressively"]
            if not raid_reduction:
                GOOD(f"✅  Raid Reduction is disabled")
            else:
                WARN(
                    "⚠️  Raid Reduction is ENABLED. Please contact Weka support for instructions on how to disable"
                )
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN(f"⚠️  Unable able to determine Raid Reduction settings")

    if V(weka_version) == V("3.9"):
        INFO("VERIFYING BUCKET L2BLOCK ENTRIES")
        compute_node = []
        spinner = Spinner("  Processing Data   ", color=colors.OKCYAN)
        spinner.start()
        try:
            weka_nodes = json.loads(
                subprocess.check_output(["weka", "cluster", "nodes", "-J"])
            )
            for node in weka_nodes:
                if node["roles"] == ["COMPUTE"] and node["status"] == "UP":
                    compute_node += re.findall(r"\d+", node["node_id"])
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
                if bucket[1]["entriesInL2Block"]["max"] > 477:
                    error_bucket += bucket
            if error_bucket:
                WARN(
                    "⚠️  L2BLOCK error entries found, please contact weka support ref WEKAPP-229504\n"
                )
                for line in error_bucket:
                    WARN(str(line))
            else:
                GOOD("✅  No error L2BLOCK entries found")
        except Exception as e:
            WARN("⚠️  Unable able to determine entriesInL2Block entries {e}")

        spinner.stop()

    INFO("VERIFYING SSD FIRMWARE")
    weka_drives = json.loads(
        subprocess.check_output(["weka", "cluster", "drive", "-J"])
    )
    bad_firmware = []
    for drive in weka_drives:
        if drive["firmware"] == "EDB5002Q":
            bad_firmware += [
                drive["disk_id"],
                drive["node_id"],
                drive["status"],
                drive["firmware"],
                drive["hostname"],
            ]

    if not bad_firmware:
        GOOD("✅  SSD Firmware check completed")
    else:
        WARN(
            "⚠️  The following SSDs might be problematic please contact Weka Support\n"
        )
        printlist(bad_firmware, 5)

    INFO("VERIFYING WEKA CLUSTER DRIVE STATUS")
    weka_drives = json.loads(
        subprocess.check_output(["weka", "cluster", "drive", "-J"])
    )
    bad_drive = []
    for drive in weka_drives:
        if drive["status"] != "ACTIVE":
            bad_drive += [
                drive["disk_id"],
                drive["node_id"],
                drive["status"],
                drive["firmware"],
                drive["hostname"],
            ]

    if not bad_drive:
        GOOD(f"✅  All drives are in OK status")
    else:
        WARN(f"The following Drives are not Active\n")
        printlist(bad_drive, 5)

    if V("4.0") <= V(weka_version) < V("4.2.1"):
        INFO("VERIFYING DRIVES CONFIGURATION")
        weka_drives = json.loads(
            subprocess.check_output(["weka", "debug", "config", "show", "disks"])
        )
        fake_drives = []
        for disk_id, drive in weka_drives.items():
            target_state = drive["_targetState"]["state"]
            committed_state = drive["_committedState"]["state"]
            lastPhaseoutGeneration = drive["lastPhaseOutGeneration"]
            lastPhaseOutSizeB = drive["lastPhaseOutSizeB"]
            sizeB = drive["sizeB"]
            if (
                target_state == "INACTIVE"
                and lastPhaseoutGeneration == "ConfigGeneration<1>"
                and lastPhaseOutSizeB != sizeB
            ):
                fake_drives.append(
                    dict(
                        disk_id=disk_id,
                        committed_state=committed_state,
                        target_state=target_state,
                        lastPhaseOutSizeB=lastPhaseOutSizeB,
                        sizeB=sizeB,
                    )
                )

        if not fake_drives:
            GOOD(f"✅  All drives configurations are valid")
        else:
            WARN(
                f"The following Drives have an invalid configuration, please contact Weka Support prior to upgrading to V4.2\n"
            )
            for fake_drive in fake_drives:
                WARN(
                    "⚠️  {disk_id} {committed_state}=>{target_state} lastPhaseOutSizeB={lastPhaseOutSizeB} sizeB={sizeB}".format(
                        **fake_drive
                    )
                )

    if V(weka_version) >= V("4.0"):
        INFO("VERIFYING DUPLICATE BACKEND CONTAINER CORE CPU IDS")

        backend_host_names = [*{bkhost.hostname for bkhost in backend_hosts}]

        def check_duplicate_core_ids(containers):
            seen_ids = set()
            for container in containers:
                for core_id in container["cores_ids"]:
                    if core_id in seen_ids:
                        return True
                    seen_ids.add(core_id)
            return False

        def validate_core_ids(containers):
            has_error = False
            host_id = None

            for container in containers:
                if 4294967295 in container["cores_ids"]:
                    if host_id is None:
                        host_id = container["cores_ids"][0]
                    elif container["cores_ids"][0] != host_id:
                        WARN(
                            f'⚠️  Container {container["container"]} core ids set to AUTO while other containers manually set to core_id. Containers should have manually assigned core ids'
                        )
                        has_error = True

            return has_error

        combined_data = {}
        container_by_host = []
        for host in backend_host_names:
            for bkhost in backend_hosts:
                if host == bkhost.hostname:
                    container_by_host.append(
                        {
                            "hostname": bkhost.hostname,
                            "container": bkhost.container,
                            "cores": bkhost.cores,
                            "cores_ids": bkhost.cores_ids,
                        }
                    )

        for item in container_by_host:
            hostname = item["hostname"]
            container_info = {
                "container": item["container"],
                "cores": item["cores"],
                "cores_ids": item["cores_ids"],
            }

            if hostname in combined_data:
                combined_data[hostname].append(container_info)
            else:
                combined_data[hostname] = [container_info]

        for hostname, containers in combined_data.items():
            if check_duplicate_core_ids(containers):
                WARN(
                    f"⚠️  Duplicate core ids found in different containers on host {hostname}."
                )

            if validate_core_ids(containers):
                WARN(
                    f"⚠️  Core ids set to AUTO in one container on host {hostname} while other containers have manually assigned core_ids."
                )

        if not any(
            check_duplicate_core_ids(containers) or validate_core_ids(containers)
            for containers in combined_data.values()
        ):
            GOOD(f"✅  No misconfigured core ids found.")

    INFO("VERIFYING WEKA TRACES STATUS")
    if V(weka_version) >= V("3.10"):
        weka_traces = json.loads(
            subprocess.check_output(["weka", "debug", "traces", "status", "-J"])
        )
        if weka_traces["enabled"]:
            GOOD(f"✅  Weka traces are enabled")
        else:
            WARN(
                '⚠️  Weka traces are NOT enabled, enable Weka traces using "weka debug traces start"'
            )
    else:
        weka_traces = subprocess.check_output(
            [
                "sudo",
                "weka",
                "local",
                "exec",
                "/usr/local/bin/supervisorctl",
                "status",
                "weka-trace-dumper",
            ]
        ).decode("utf-8")
        if "RUNNING" in weka_traces:
            GOOD(f"✅  Weka traces are enabled")
        else:
            WARN(
                '⚠️  Weka traces are NOT enabled, enable Weka traces using "weka local exec '
                + '/usr/local/bin/supervisorctl stop weka-trace-dumper"'
            )

    if V(weka_version) >= V("3.9"):
        INFO("CHECKING FOR MANUAL WEKA OVERRIDES")
        override_list = []
        manual_overrides = json.loads(
            subprocess.check_output(["weka", "debug", "override", "list", "-J"])
        )
        if manual_overrides:
            WARN("Manual Weka overrides found")
            for override in manual_overrides:
                override_list += [
                    override["override_id"],
                    override["key"],
                    override["value"],
                    override["bucket_id"],
                    override["enabled"],
                ]

        else:
            GOOD("✅  No manual Weka overrides found")
    if override_list:
        printlist(override_list, 5)

    INFO("CHECKING FOR WEKA BLACKLISTED NODES")
    blacklist = []
    if weka_info["nodes"]["blacklisted"] == 0:
        GOOD(f"✅  No Weka blacklisted nodes found")
    else:
        WARN(f"Weka blacklisted nodes found\n")
        blacklist_list = json.loads(
            subprocess.check_output(["weka", "debug", "blacklist", "list", "-J"])
        )
        for nodes in blacklist_list:
            blacklist += [
                nodes["node_id"],
                nodes["hostname"],
                nodes["ips"],
                nodes["status"],
                nodes["network_mode"],
            ]

    if blacklist:
        printlist(blacklist, 5)

    if V("3.14") <= V(weka_version) < V("4.2.7"):
        INFO("CHECKING WEKA STATS RETENTION")
        stats_retention = json.loads(
            subprocess.check_output(["weka", "stats", "retention", "status", "-J"])
        )
        if stats_retention["retention_secs"] <= 172800:
            GOOD("✅  Weka stats retention settings are set correctly")
        else:
            WARN(
                '⚠️  Set stats retention to 1 days, execute "weka stats retention set --days 1". Following '
                + 'the upgrade revert back using "weka stats retention set --days '
                + '{int(stats_retention["retention_secs"] / 86400)}'
            )

    if V(weka_version) >= V("3.12") and weka_info["hosts"]["total_count"] >= 100:
        INFO("VERIFYING TLS SETTINGS")
        try:
            wekacfg = json.loads(
                subprocess.check_output(
                    [
                        "sudo",
                        "weka",
                        "local",
                        "run",
                        "--container",
                        running_container[0],
                        "--",
                        "/weka/cfgdump",
                    ]
                )
            )
            if (wekacfg["serializedTLSData"]["state"]) == "NONE":
                GOOD("✅  TLS is Disabled")
            else:
                WARN(
                    "⚠️  TLS is Enabled and should be disabled please contact Weka Support"
                )
        except (ValueError, RuntimeError, TypeError, NameError):
            WARN(f"⚠️  Unable able to determine TLS state")

    INFO("VERIFING HOSTS MACHINE IDENTIFIERS")
    spinner = Spinner("  Retrieving Data  ", color=colors.OKCYAN)
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
        BAD(f'{" " * 5}❌  Duplicate machine identifiers found for hosts:')
        for hostname in duplicate_identifiers:
            BAD(f'{" " * 10}-> {hostname}')
    else:
        GOOD(f'{" " * 5}✅  Machine identifiers check complete')

    spinner.stop()

    s3_status = False

    s3_cluster_status = json.loads(
        subprocess.check_output(["weka", "s3", "cluster", "-J"])
    )

    if V(weka_version) > V("3.13"):
        s3_status = s3_cluster_status["active"]

    if s3_status:
        bad_s3_hosts = []
        failed_s3host = []
        INFO("CHECKING WEKA S3 CLUSTER HEALTH")
        s3_cluster_hosts = json.loads(
            subprocess.check_output(["weka", "s3", "cluster", "status", "-J"])
        )
        for host, status in s3_cluster_hosts.items():
            if not status:
                bad_s3_hosts.append(host)

        if not bad_s3_hosts:
            GOOD(f'{" " * 5}✅  No failed s3 hosts found')
        else:
            WARN(f'{" " * 5}⚠️  Found s3 cluster hosts in not ready status:\n')
            for s3host in bad_s3_hosts:
                for bkhost in backend_hosts:
                    if s3host == bkhost.typed_id:
                        failed_s3host.append(
                            dict(
                                id=bkhost.typed_id,
                                hostname=bkhost.hostname,
                                ip=bkhost.ip,
                                version=bkhost.sw_version,
                                mode=bkhost.mode,
                            )
                        )

                for host_info in failed_s3host:
                    WARN(
                        f'{" " * 5}⚠️  Host: {host_info["id"]} {host_info["hostname"]} {host_info["ip"]} {host_info["version"]} {host_info["mode"]}'
                    )

    if s3_status:
        INFO("CHECKING WEKA S3 MOUNT OPTIONS")
        s3_mount_options = json.loads(
            subprocess.check_output(["weka", "s3", "cluster", "-J"])
        )
        mount_options = s3_mount_options["mount_options"]
        if "writecache" in mount_options:
            WARN(
                f'{" " * 5}⚠️  S3 mount options set incorrectly please contact weka support prior to upgrade'
            )
        else:
            GOOD(f'{" " * 5}✅  S3 mount options set correctly')

    smb_cluster_hosts = json.loads(
        subprocess.check_output(["weka", "smb", "cluster", "status", "-J"])
    )

    if V(weka_version) > V("3.10"):
        if len(smb_cluster_hosts) != 0:
            INFO("CHECKING WEKA SMB CLUSTER HOST HEALTH")
            bad_smb_hosts = []
            failed_smbhosts = []
            for host, status in smb_cluster_hosts.items():
                if not status:
                    bad_smb_hosts += [host]

            if not bad_smb_hosts:
                GOOD(f'{" " * 5}✅  No failed SMB hosts found')
            else:
                WARN(f'{" " * 5}⚠️  Found SMB cluster hosts in not ready status:\n')
                for smbhost in bad_smb_hosts:
                    for bkhost in backend_hosts:
                        if smbhost == bkhost.typed_id:
                            failed_smbhosts.append(
                                dict(
                                    id=bkhost.typed_id,
                                    hostname=bkhost.hostname,
                                    ip=bkhost.ip,
                                    version=bkhost.sw_version,
                                    mode=bkhost.mode,
                                )
                            )

                for host_info in failed_smbhosts:
                    WARN(
                        f'{" " * 5}⚠️  Host: {host_info["id"]} {host_info["hostname"]} {host_info["ip"]} {host_info["version"]} {host_info["mode"]}'
                    )

    nfs_server_hosts = json.loads(
        subprocess.check_output(["weka", "nfs", "interface-group", "-J"])
    )

    if V(weka_version) > V("3.10"):
        if len(nfs_server_hosts) != 0:
            INFO("CHECKING WEKA NFS SERVER HEALTH")
            if nfs_server_hosts[0]["status"] == "OK":
                GOOD(f'{" " * 5}✅  NFS Server status OK')
            elif nfs_server_hosts[0]["status"] == "Inactive":
                WARN(
                    f'{" " * 5}⚠️  NFS Server {nfs_server_hosts[0]["name"]} is {nfs_server_hosts[0]["status"]}'
                )
            else:
                WARN(f'{" " * 5}⚠️  NFS Server {nfs_server_hosts[0]["name"]} Not OK')

            if nfs_server_hosts[0]["status"] != "Inactive":
                INFO("CHECKING WEKA NFS SERVER HOST HEALTH")
                bad_nfs_hosts = []
                failed_nfshosts = []
                for host in nfs_server_hosts[0]["ports"]:
                    if host["status"] != "OK":
                        bad_nfs_hosts += [host["host_id"]]

                if not bad_nfs_hosts:
                    GOOD(f'{" " * 5}✅  No failed NFS hosts found')
                else:
                    WARN(f'{" " * 5} Found NFS cluster hosts in bad status:\n')
                    for nfshost in bad_nfs_hosts:
                        for bkhost in backend_hosts:
                            if nfshost == bkhost.typed_id:
                                failed_nfshosts.append(
                                    dict(
                                        id=bkhost.typed_id,
                                        hostname=bkhost.hostname,
                                        ip=bkhost.ip,
                                        version=bkhost.sw_version,
                                        mode=bkhost.mode,
                                    )
                                )

                    for host_info in failed_nfshosts:
                        WARN(
                            f'{" " * 5}⚠️  Host: {host_info["id"]} {host_info["hostname"]} {host_info["ip"]} {host_info["version"]} {host_info["mode"]}'
                        )

    # need to understand how to handle exception.
    if s3_status:
        if V(weka_version) < V("4.1"):
            INFO("CHECKING ETCD ENDPOINT HEALTH")
            spinner = Spinner("  Retrieving Data  ", color=colors.OKCYAN)
            spinner.start()

            if s3_cluster_status["active"]:
                etcd_status = []
                output = None
                retcode = subprocess.call(
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
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )

                if retcode == 0:
                    etcd_status = json.loads(
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
                    )
                    for status in etcd_status:
                        if not status["health"]:
                            WARN(
                                f'{" " * 5}⚠️  ETCD member on {status["endpoint"]} is down'
                            )
                        else:
                            GOOD(
                                f'{" " * 5}✅  ETCD members are healthy {status["endpoint"]}'
                            )
                else:
                    WARN(
                        f'{" " * 5}⚠️  ETCD DB is not healthy or not running please contact Weka support'
                    )

            spinner.stop()

    return (
        backend_hosts,
        ssh_bk_hosts,
        client_hosts,
        ssh_cl_hosts,
        weka_info,
        check_version,
        backend_ips,
        s3_status,
    )


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
                "8.2",
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
                "20.04.1",
            ],
            "amzn": ["17.09", "17.12", "18.03", "2"],
        },
        "clients_only": {
            "sles": ["12.5", "15.2"],
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
                "8.7",
            ],
            "rocky": ["8.6", "8.7"],
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
            "amzn": ["17.09", "17.12", "18.03", "2"],
        },
        "clients_only": {
            "sles": ["12.5", "15.2"],
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
                "8.7",
            ],
            "rocky": ["8.6", "8.7"],
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
            "amzn": ["17.09", "17.12", "18.03", "2"],
        },
        "clients_only": {
            "sles": ["12.5", "15.2"],
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
                "8.7",
            ],
            "rocky": ["8.6", "8.7"],
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
            ],
            "amzn": ["17.09", "17.12", "18.03", "2"],
        },
        "clients_only": {
            "sles": ["12.5", "15.2"],
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
                "8.7",
            ],
            "rocky": ["8.6", "8.7"],
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
                "20.04.5",
            ],
            "amzn": ["17.09", "17.12", "18.03", "2"],
        },
        "clients_only": {
            "sles": ["12.5", "15.2"],
        },
    },
    "4.2": {
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
                "8.7",
            ],
            "rocky": ["8.6", "8.7", "9.1"],
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
                "20.04.5",
                "22.04.3",
                "22.04.4",
            ],
            "amzn": ["17.09", "17.12", "18.03", "2"],
        },
        "clients_only": {
            "sles": ["12.5", "15.2"],
        },
    },
    "4.3": {
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
                "8.7",
                "8.8",
                "9.0",
                "9.1",
                "9.2",
            ],
            "rocky": [
                "8.6",
                "8.7",
                "8.8",
                "8.9",
                "9.0",
                "9.1",
                "9.2",
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
                "20.04.5",
                "22.04.0",
                "22.04.1",
                "22.04.2",
                "22.04.3",
                "22.04.4",
                "22.04.6",
            ],
            "amzn": ["17.09", "17.12", "18.03", "2"],
        },
        "clients_only": {
            "sles": ["12.5", "15.2"],
        },
    },
}


def ssh_check(host_name, result, ssh_bk_hosts):
    passwordless_ssh = result
    if passwordless_ssh != 0:
        BAD(
            f'{" " * 5}❌  Password SSH not configured on host: {host_name}, will exclude from checks'
        )
        ssh_bk_hosts = [x for x in ssh_bk_hosts if x["name"] != host_name]
    else:
        GOOD(f'{" " * 5}✅  Password SSH configured on host: {host_name}')

    return ssh_bk_hosts


check_rhel_systemd_hosts = []


def check_os_release(
    host_name, result, weka_version, check_version, backend=True, client=False
):
    global check_rhel_systemd_hosts
    if "CentOS" in result:
        result = result.split()
        version = result[3].split(".")
        version = ".".join(version[:2])

        if backend:
            if version not in supported_os[check_version]["backends_clients"]["centos"]:
                BAD(
                    f'{" " * 5}❌  Host {host_name} OS CentOS {version} is not supported with '
                    f"weka version {weka_version}"
                )
            else:
                GOOD(
                    f'{" " * 5}✅  Host {host_name} OS CentOS {version} is supported with '
                    f"weka version {weka_version}"
                )
        elif client:
            if (
                version not in supported_os[check_version]["backends_clients"]["centos"]
                and supported_os[check_version]["clients_only"]["centos"]
            ):
                BAD(
                    f'{" " * 5}❌  Host {host_name} OS CentOS {version} is not supported with '
                    f"weka version {weka_version}"
                )
            else:
                GOOD(
                    f'{" " * 5}✅  Host {host_name} OS CentOS {version} is supported with '
                    f"weka version {weka_version}"
                )

    else:
        info_str = result.replace("=", ":")
        info_list = [item for item in info_str.split("\n") if item]

        dict_info = {}
        for item in info_list:
            key, value = item.split(":", 1)
            dict_info[key] = value.strip('"')

        os_id = dict_info["ID"]
        version = dict_info.get("VERSION_ID", "Unknown")

        # Match version for Ubuntu
        if os_id == "ubuntu":
            version_match = re.search(r"\b\d+(\.\d+){0,2}\b", dict_info["VERSION"])
            version = version_match.group() if version_match else "Unknown"

        # Handling Rocky or RHEL
        elif os_id in ["rocky", "rhel"] and float(version) >= 9.0:
            check_rhel_systemd_hosts.append(host_name)

        # OS validation for backends
        if backend:
            if os_id not in supported_os[check_version]["backends_clients"]:
                BAD(f'{" " * 5}❌  Host {host_name} OS {os_id} is not recognized')
            elif version not in supported_os[check_version]["backends_clients"][os_id]:
                BAD(
                    f'{" " * 5}❌  Host {host_name} OS {os_id} {version} is not supported with '
                    f"weka version {weka_version}"
                )
            else:
                GOOD(
                    f'{" " * 5}✅  Host {host_name} OS {os_id} {version} is supported with '
                    f"weka version {weka_version}"
                )

        # OS validation for clients
        elif client:
            if (
                version not in supported_os[check_version]["backends_clients"][os_id]
                and supported_os[check_version]["clients_only"][os_id]
            ):
                BAD(
                    f'{" " * 5}❌  Host {host_name} OS {os_id} {version} is not supported with '
                    f"weka version {weka_version}"
                )
            else:
                GOOD(
                    f'{" " * 5}✅  Host {host_name} OS {os_id} {version} is supported with '
                    f"weka version {weka_version}"
                )


def weka_agent_unit_type(host_name, result):
    result_lines = result.splitlines()
    SRV = None

    for line in result_lines:
        if line.startswith("SRV="):
            SRV = line.split("=", 1)[1]
            break

    if SRV == "init.d":
        GOOD(
            f'{" " * 5}✅  Host {host_name}: weka-agent.service running as init.d service'
        )
    elif SRV == "systemd":
        BAD(
            f'{" " * 5}❌  Host {host_name} weka-agent.service running as systemd service, please contact weka support prior to upgrade'
        )
    else:
        WARN(
            f'{" " * 5}⚠️  Host {host_name}: Unable to determine weka-agent service type'
        )


def weka_agent_check(host_name, result):
    weka_agent_status = result
    if weka_agent_status != 0:
        BAD(f'{" " * 5}❌  Weka Agent Service is NOT running on host: {host_name}')
    else:
        GOOD(f'{" " * 5}✅  Weka Agent Service is running on host: {host_name}')


def time_check(host_name, result):
    current_time = result
    local_lime = int(time.time())
    if abs(int(current_time) - local_lime) > 60:
        BAD(f'{" " * 5}❌  Time difference greater than 60s on host: {host_name}')
    else:
        GOOD(f'{" " * 5}✅  Time check passed on host: {host_name}')


def client_mount_check(host_name, result):
    if int(result) > 0:
        BAD(f'{" " * 5}❌  Found wekafs mounted on /weka for host: {host_name}')
    else:
        GOOD(f'{" " * 5}✅  No wekafs mounted on /weka for host: {host_name}')


results_lock = threading.Lock()


def free_space_check_data(results):
    results_by_host = {}
    for host_name, result in results:
        with results_lock:
            if host_name not in results_by_host:
                results_by_host[host_name] = []
            results_by_host[host_name].append(result.strip())

    for host_name, result_list in results_by_host.items():
        if len(result_list) >= 2:
            weka_partition = int(result_list[0])
            weka_data_dir = int(result_list[1]) if result_list[1] else 0
            free_capacity_needed = weka_data_dir * 1.5
            if free_capacity_needed > weka_partition:
                WARN(
                    f'{" " * 5}⚠️  Host: {host_name} does not have enough free capacity, need to free up '
                    + f"~{(free_capacity_needed - weka_partition) / 1000}G"
                )
            else:
                GOOD(f'{" " * 5}✅  Host: {host_name} has adequate free space')
        else:
            WARN(f'{" " * 5}⚠️  Insufficient data for host: {host_name}')


def free_space_check_logs(results):
    for result in results:
        hname = result[0]
        result = result[1].split(" ")
        logs_partition_used = int(result[0])
        free_capacity_needed = logs_partition_used * 1.5
        logs_partition_available = int(result[1])
        if (free_capacity_needed) > (logs_partition_available):
            WARN(
                f'{" " * 5}⚠️  Host: {hname} does not have enough free capacity, need to free up '
                + f"~{(free_capacity_needed - logs_partition_available) / 1000}G"
            )
        else:
            GOOD(f'{" " * 5}✅  Host: {hname} has adequate free space')


def weka_container_status(results, weka_version):
    containers_by_host = {
        host: [
            dict(
                name=containers["name"],
                isRunning=containers["isRunning"],
                isDisabled=containers["isDisabled"],
                type=containers["type"],
            )
            for containers in result
        ]
        for host, result in results
    }
    for host in containers_by_host.items():
        host_name = host[0]
        containers = host[1]
        INFO2(f'{" " * 2}Checking weka container status on host {host_name}:')
        for container in containers:
            name = container["name"]
            is_running = container["isRunning"]
            is_disabled = container["isDisabled"]
            container_status = "Running" if is_running else "Stopped"
            disabled = "True" if is_disabled else "False"
            if V(weka_version) >= V("4.1"):
                if (
                    disabled == "True"
                    or container_status == "Stopped"
                    or name == "upgrade"
                ):
                    BAD(
                        f'{" " * 5}❌  Container {name}: {container_status} and Disabled={disabled}'
                    )
                else:
                    GOOD(
                        f'{" " * 5}✅  Container {name}: {container_status} and Disabled={disabled}'
                    )
            else:
                type = container["type"]
                if (
                    type == "weka"
                    and disabled == "False"
                    or container_status == "Running"
                ):
                    GOOD(
                        f'{" " * 5}✅  Container {name}: {container_status} and Disabled={disabled}'
                    )
                elif name == "upgrade":
                    BAD(
                        f'{" " * 5}❌  Container {name}: {container_status} and Disabled={disabled}'
                    )
                elif type != "weka" and disabled == "False":
                    BAD(
                        f'{" " * 5}❌  Container {name}: {container_status} and Disabled={disabled}'
                    )


def weka_mounts(results):
    new_results = dict(results)
    for item in new_results.items():
        host_name = item[0]
        mounts = item[1].split("\n")
        INFO2(f'{" " * 2} Checking for mounted Weka filesystems on host {host_name}:')
        if mounts == [""]:
            GOOD(f'{" " * 5}✅  No mounted Weka filesystems found')
        else:
            for mount in mounts:
                WARN(f'{" " * 5}⚠️  Found Weka filesytems mounted {mount}')


def get_host_name(host_id, backend_hosts):
    return next(
        (bkhost.hostname for bkhost in backend_hosts if host_id == bkhost.typed_id),
        "",
    )


def frontend_check(host_name, result):
    frontend_mounts = result
    if frontend_mounts != "0":
        WARN(
            f'{" " * 5}⚠️  Weka frontend process in use on host: {host_name}, contact Weka Support prior to upgrading'
        )
    else:
        GOOD(f'{" " * 5}✅  Weka frontend process OK on host: {host_name}')


def protocol_host(backend_hosts, s3_enabled):
    S3 = []
    global weka_s3, weka_nfs, weka_smb
    s3_enabled = json.loads(subprocess.check_output(["weka", "s3", "cluster", "-J"]))
    if s3_enabled:
        weka_s3 = json.loads(
            subprocess.check_output(["weka", "s3", "cluster", "status", "-J"])
        )
        if weka_s3:
            S3 = list(weka_s3)

    weka_smb = json.loads(subprocess.check_output(["weka", "smb", "cluster", "-J"]))
    SMB = list(weka_smb["sambaHosts"]) if weka_smb != [] else []
    NFS = []
    weka_nfs = json.loads(
        subprocess.check_output(["weka", "nfs", "interface-group", "-J"])
    )
    if weka_nfs:
        NFS = [hid["host_id"] for host_id in weka_nfs for hid in host_id["ports"]]

    combined_lists = [S3, SMB, NFS]

    total_protocols = {}
    protocol_type = ["s3", "smb", "nfs"]

    for i, lst in enumerate(combined_lists):
        for elem in lst:
            if elem in total_protocols:
                total_protocols[elem]["freq"] += 1
                total_protocols[elem]["lists"].append(protocol_type[i])
            else:
                total_protocols[elem] = {"freq": 1, "lists": [protocol_type[i]]}

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
        num_proto = multiprotocols[host_name]["freq"]
        protos = multiprotocols[host_name]["lists"]
        if num_proto > 1:
            WARN(
                f'{" " * 5}⚠️  Host: {host_name} is running {num_proto} protocols {protos} recommended is 1'
            )
        elif num_proto == 1:
            GOOD(
                f'{" " * 5}✅  Host: {host_name} is running {num_proto} protocols {protos}'
            )

    for host_name in protocol_host_names:
        if host_name in list(dict.fromkeys(multiprotocols)):
            continue
        GOOD(f'{" " * 5}✅  Host: {host_name} is running 0 protocols')


def client_web_test(results):
    new_results = dict(results)
    for item in new_results.items():
        client_name = item[0]
        http_status_code = item[1]
        if http_status_code == "200":
            GOOD(
                f'{" " * 5}✅  Client web connectivity check passed on host: {client_name}'
            )
        else:
            WARN(
                f'{" " * 5}⚠️  Client web connectivity check failed on host: {client_name}'
            )


def invalid_endpoints(host_name, result, backend_ips):
    result = (
        result.replace(", ]}]", "]}]")
        .replace("container", '"container"')
        .replace(" ip:", '"ip":')
        .replace(" {", ' "')
        .replace("},", '",')
    )

    result = result.split("\n")[:]

    def ip_by_containers(result):
        INFO2("{}Validating endpoint-ips on host {}:".format(" " * 2, host_name))
        for line in result:
            endpoint_data = json.loads(line)
            bad_backend_ip = []
            for container, ips in endpoint_data:
                container = endpoint_data[0]["container"]
                ips = endpoint_data[0]["ip"]
                for ip in ips:
                    if ip not in backend_ips or ip == "0.0.0.0":
                        bad_backend_ip += [ip]

                if bad_backend_ip == []:
                    GOOD(
                        f'{" " * 5}✅  No invalid endpoint ips found on host: {host_name} container: {container}'
                    )
                else:
                    WARN(
                        f'{" " * 5}⚠️  Invalid endpoint ips found on host: {host_name} container: '
                        + f"{container} invalid ips: {bad_backend_ip}"
                    )

    ip_by_containers(result)


all_secrets = []
container_data = {}


def check_join_secrets(results):
    global container_data

    # Convert the list of tuples into a dictionary
    for host, json_str in results:
        try:
            cleaned_json_str = json_str.strip()
            parsed_data = json.loads(cleaned_json_str)
            container_data[host] = parsed_data

            # Collect all secrets globally
            for container, secrets in parsed_data.items():
                secret_set = set(secrets)
                if secret_set:
                    all_secrets.extend(secret_set)

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for host {host}: {e}")
            continue


def find_key_secret():
    """
    Identify the most common secret globally.
    """
    secret_counter = Counter(all_secrets)
    if secret_counter:
        key_secret, _ = secret_counter.most_common(1)[0]
    else:
        key_secret = None
    return key_secret


def compare_global_secrets(hosts_data, key_secret):
    missing_secrets = []
    for host_name, result in hosts_data.items():
        for container, secrets in result.items():
            secret_set = set(secrets)
            if not secret_set:  # If the secret set is empty
                missing_secrets.append((host_name, container, "missing"))
            elif (
                key_secret not in secret_set
            ):  # If the key secret isn't found in the container's secrets
                missing_secrets.append(
                    (host_name, container, "does not match key secret")
                )
    return missing_secrets


def data_dir_check(host_name, result):
    directory_by_host = {host_name: []}
    for line in result.splitlines():
        usage = int(line.split("\t")[0])
        directory = line.split("\t")[1].split("/")[4]
        item_list = [directory, usage]
        directory_by_host[host_name].append(item_list)

    for key, value in directory_by_host.items():
        INFO2(f'{" " * 2}Checking weka container status on host {key}:')
        for sublist in value:
            dir = sublist[0]
            use = sublist[1]
            if use < 10000:
                GOOD(f'{" " * 5}✅  Data directory {dir} acceptable size {use} MB')
            else:
                WARN(
                    f'{" " * 5}⚠️  Data directory {dir} larger than acceptable size {use} MB'
                )


def weka_traces_size(host_name, result):
    weka_trace_status = json.loads(
        subprocess.check_output(["weka", "debug", "traces", "status", "-J"])
    )
    weka_trace_ensure_free = weka_trace_status["servers_ensure_free"]["value"]
    INFO2(f'{" " * 2}Checking free space for Weka traces on Host: {host_name}:')
    if weka_trace_ensure_free > int(result) * 1024:
        WARN(
            f'{" " * 5}⚠️  Weka trace ensure free size of {weka_trace_ensure_free} is greater than Weka trace directory size of {int(result)*1024}'
        )
    else:
        GOOD(f'{" " * 5}✅  Weka trace size OK')


def cgroup_version(hostname, result):
    INFO2(f'{" " * 2}Checking Cgroup version on host {hostname}:')
    if result == "tmpfs":
        GOOD(f'{" " * 5}✅  Correct cgroup v1 set')
    elif result == "cgroup2fs":
        BAD(f'{" " * 5}❌  Incorrect cgroup v2 set')
    else:
        WARN(f'{" " * 5}⚠️  Unable to determine cgroup version')


def cpu_instruction_set(host_name, result):
    INFO2(f'{" " * 2}Validating cpu instruction set on Host: {host_name}:')
    if result is None or "":
        BAD(
            f'{" " * 5}❌  Cannot update to Weka version 4.3 cpu instruction set avx2 missing'
        )
    else:
        GOOD(f'{" " * 5}✅  Cpu instruction set validation successful')


def check_os_kernel(host_name, result):
    result_lines = result.splitlines()
    P = None
    for line in result_lines:
        if line.startswith("P="):
            P = line.split("=", 1)[1]
            break

    if P == "true":
        BAD(
            f'{" " * 5}❌  Host {host_name} kernel level not supported, please contact weka support prior to upgrade'
        )
    elif P == "false" or "not_rocky":
        GOOD(f'{" " * 5}✅  Host {host_name}: kernel level supports upgrade')


def endpoint_status(host_name, result):
    result_lines = result.splitlines()
    P = None
    for line in result_lines:
        if line.startswith("P="):
            P = line.split("=", 1)[1]
            break

    if P == "running":
        WARN(
            f'{" " * 5}⚠️  Host {host_name} CrowdStrike Falcon Sensor is running, recommended to stop the service prior to upgrade'
        )
    elif P == "loaded":
        WARN(
            f'{" " * 5}⚠️  Host {host_name} CrowdStrike Falcon Sensor kernel module loaded'
        )
    elif P == "not_running":
        GOOD(f'{" " * 5}✅  Host {host_name}: Endpoint validation complete')


def host_port_connectivity(results):
    port_status_by_host = {}
    for host, port_info in results:

        if host not in port_status_by_host:
            port_status_by_host[host] = []

        port_status_by_host[host].append(port_info)

    for host, port_list in port_status_by_host.items():
        INFO2(f"Checking weka port connectivity on host {host}:")
        for port_info in port_list:
            status, port = port_info.split()
            if status == "0":
                GOOD(f'{" " * 5}✅  Connectivity to port {port} ok')
            else:
                BAD(
                    f'{" " * 5}❌  Host Connectivity to port {port} not ok, error {status} need to restart protocol container on Host: {host}'
                )


def parallel_execution(
    hosts,
    commands,
    use_check_output=True,
    use_json=False,
    use_call=False,
    ssh_identity=None,
):
    results = []
    spinner = Spinner("  Retrieving Data  ", color=colors.OKCYAN)
    spinner.start()

    SSH_OPTIONS = [
        ["-o", "PasswordAuthentication=no"],
        ["-o", "LogLevel=ERROR"],
        ["-o", "UserKnownHostsFile=/dev/null"],
        ["-o", "StrictHostKeyChecking=no"],
        ["-o", "ConnectTimeout=10"],
    ]

    ssh_opts = SSH_OPTIONS

    if ssh_identity:
        ssh_opts += [["-i", ssh_identity]]

    def run_command(host, command, use_check_output, use_json, use_call, ssh_opts):
        if isinstance(host, dict):
            host_ip = host["ip"]
            host_name = host["name"]
        else:
            host_ip = host
            host_name = host

        ssh_opts_flat = list(itertools.chain(*ssh_opts))

        if use_check_output:
            result = (
                subprocess.check_output(["ssh"] + ssh_opts_flat + [host_ip, command])
                .decode("utf-8")
                .strip()
            )
        elif use_json:
            result = json.loads(
                subprocess.check_output(["ssh"] + ssh_opts_flat + [host_ip, command])
                .decode("utf-8")
                .strip()
            )
        elif use_call:
            result = subprocess.call(
                ["ssh"] + ssh_opts_flat + [host_ip, command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        else:
            result = subprocess.run(
                ["ssh"] + ssh_opts_flat + [host_ip, command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        return host_name, result

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        future_to_host = {
            executor.submit(
                run_command,
                host,
                command,
                use_check_output,
                use_json,
                use_call,
                ssh_opts,
            ): host
            for host in hosts
            for command in commands
        }
        for future in concurrent.futures.as_completed(future_to_host):
            host = future_to_host[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                host_name = host["name"] if isinstance(host, dict) else host
                WARN(f'{" " * 5}⚠️  Unable to determine Host: {host_name} results')

    spinner.stop()
    return results


# backend checks
def backend_host_checks(
    backend_hosts,
    ssh_bk_hosts,
    weka_version,
    check_version,
    backend_ips,
    ssh_identity,
    s3_enabled,
    check_rhel_systemd_hosts,
):
    INFO("CHECKING PASSWORDLESS SSH CONNECTIVITY")
    results = parallel_execution(
        ssh_bk_hosts,
        ["/bin/true"],
        use_check_output=False,
        use_call=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is not None:
            ssh_bk_hosts = ssh_check(host_name, result, ssh_bk_hosts)
        else:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")

    if len(ssh_bk_hosts) == 0:
        BAD(f'{" " * 5}❌  Unable to proceed, Password SSH not configured on any host')
        sys.exit(1)

    if V(weka_version) >= V("3.12"):
        INFO("CHECKING IF OS IS SUPPORTED ON BACKENDS")
        command = r"""
        OS=$(sudo cat /etc/os-release | awk -F= '/^ID=/ {print $2}' > /dev/null);
        if [[ $OS == "centos" ]]; then
            sudo cat /etc/centos-release;
        else
                sudo cat /etc/os-release;
        fi
        """
        results = parallel_execution(
            ssh_bk_hosts,
            [command],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is not None:
                check_os_release(
                    host_name, result, weka_version, check_version, backend=True
                )
            else:
                WARN(f"Unable to determine Host: {host_name} OS version")

    relevant_hosts = [host for host in check_rhel_systemd_hosts]

    if check_rhel_systemd_hosts:
        INFO("CHECKING IF WEKA AGENT SERVICE TYPE")
        command = r"""
        if [ -f "/etc/init.d/weka-agent" ]; then
            echo "SRV=init.d";
        else
            echo "SRV=systemd";
        fi
        """
        results = parallel_execution(
            relevant_hosts,
            [command],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is not None:
                weka_agent_unit_type(host_name, result)
            else:
                WARN(
                    f"Unable to determine Host: {host_name} weka agent service unit type"
                )

    INFO("CHECKING WEKA AGENT STATUS ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts,
        ["sudo service weka-agent status"],
        use_check_output=False,
        use_call=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is not None:
            weka_agent_check(host_name, result)
        else:
            WARN(f"Unable to determine Host: {host_name} weka-agent status")

    INFO("CHECKING TIME DIFFERENCE ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts,
        ["date --utc +%s"],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is not None:
            time_check(host_name, result)
        else:
            WARN(f"Unable to determine time on Host: {host_name}")

    INFO("CHECKING WEKA DATA DIRECTORY SPACE USAGE ON BACKENDS")
    if V(weka_version) >= V("4.2.7"):
        data_dir = "/opt/weka/data/"
        excluded_dirs = {
            "envoy",
            "smbw",
            "ganesha",
            "agent",
            "dependencies",
            "ofed",
            "igb_uio",
            "logs.loop",
            "mpin_user",
            "pkg_tools",
            "uio_generic",
            "weka_driver",
        }
        subdirectories = [
            d for d in os.listdir(data_dir) if "_" not in d and d not in excluded_dirs
        ]

        commands = ["df -m /opt/weka | awk 'NR==2 {print $4}'"] + [
            f"sudo du -smc /opt/weka/data/{d} 2>&1 | grep -v  '^du:' | awk '/total/ {{print $1}}'"
            for d in subdirectories
        ]

        results = parallel_execution(
            ssh_bk_hosts,
            commands,
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to determine Host: {host_name} available space")

        free_space_check_data(results)

    else:
        data_dir = f"/opt/weka/data/*_{str(weka_version)}"
        commands = [
            "df -m /opt/weka | awk 'NR==2 {print $4}'",
            f"sudo du -smc {data_dir} 2>&1 | grep -v  '^du:' | awk '/total/ {{print $1}}'",
        ]

        results = parallel_execution(
            ssh_bk_hosts,
            commands,
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to determine Host: {host_name} available space")

        free_space_check_data(results)

    INFO("CHECKING WEKA LOGS DIRECTORY SPACE USAGE ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts,
        ["df -m /opt/weka/logs/ | awk 'NR==2 {print $3, $4}'"],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine Host: {host_name} available space")

    free_space_check_logs(results)

    INFO("CHECKING BACKEND WEKA CONTAINER STATUS ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts,
        ["weka local ps -J"],
        use_check_output=False,
        use_json=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine Host: {host_name} weka container status")

    if results != []:
        weka_container_status(results, weka_version)

    INFO("CHECKING FOR WEKA MOUNTS ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts,
        ["sudo mount -t wekafs | awk '{print $1, $2, $3}'"],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")

    weka_mounts(results)

    if V(weka_version) < V("4.1"):
        INFO("CHECKING IF WEKA FRONTEND IN USE")
        results = parallel_execution(
            ssh_bk_hosts,
            ['find /sys/class/bdi -name "wekafs*" | wc -l'],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is not None:
                frontend_check(host_name, result)
            else:
                WARN(f"Unable to determine frontend status on Host: {host_name}")

    INFO("CHECKING NUMBER OF RUNNING PROTOCOLS ON BACKENDS")
    protocol_host(backend_hosts, s3_enabled)

    INFO("CHECKING FOR INVALID ENDPOINT IPS ON BACKENDS")
    results = parallel_execution(
        ssh_bk_hosts,
        [
            "container_name=$(weka local ps --no-header -o name| egrep -v 'samba|s3|ganesha|envoy'); for name in $container_name; do echo -en [{container: {$name}, ip: [; sudo weka local resources --stable --container $name -J | grep -w ip | awk '{print $2}' | tr '\n' ' '; echo -e ]}]; done"
        ],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")
        else:
            invalid_endpoints(host_name, result, backend_ips)

    INFO("CHECKING FOR MISSING / INVALID JOIN-SECRETS ON BACKENDS")
    command = r"""
    container_name=$(weka local ps --no-header -o name | egrep -v 'samba|s3|ganesha|envoy|smbw');
    echo -n "{";
    first=true;
    for cname in $container_name; do
        if [ "$first" = true ]; then first=false; else echo -n ","; fi
        echo -n "\"$cname\":";

        # Determine if Python or Python3 is available
        python_cmd=""
        if command -v python &>/dev/null; then
            python_cmd="python"
        elif command -v python3 &>/dev/null; then
            python_cmd="python3"
        else
            echo "[]";
            continue
        fi

        join_secret=$(sudo weka local resources -C "$cname" -J | $python_cmd -c 'import sys, json; resource = sys.stdin.read(); data = json.loads(resource); join_secret = data.get("join_secret", []); print(json.dumps(join_secret))')

        echo -n "$join_secret"
    done;
    echo -n "}"
    """
    results = parallel_execution(
        ssh_bk_hosts,
        [command],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")

    check_join_secrets(results)
    key_secret = find_key_secret()
    if not key_secret:
        GOOD(f'{" " * 5}✅  No secret found across all hosts')
    else:
        INFO2(f"Global key secret: {key_secret}")

        missing_secrets = compare_global_secrets(container_data, key_secret)

        if missing_secrets:
            INFO2("Hosts with missing or non-matching secrets:")
            for host_name, container, issue in missing_secrets:
                WARN(
                    f'{" " * 5}⚠️  "Host: {host_name}, Container: {container}, Issue: {issue}'
                )
        else:
            GOOD(f'{" " * 5}✅  All containers on all hosts have matching secrets')

    INFO("CHECKING WEKA DATA DIRECTORY SIZE ON BACKENDS")
    data_dir = "/opt/weka/data/"

    if V(weka_version) >= V("4.2.7"):
        results = parallel_execution(
            ssh_bk_hosts,
            [
                f'for name in $(weka local ps --no-header -o name | egrep -v "samba|smbw|s3|ganesha|envoy"); do du -sm {data_dir}"$name" 2>&1 | grep -v  "^du:"; done'
            ],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
    else:
        results = parallel_execution(
            ssh_bk_hosts,
            [
                f'for name in $(weka local ps --no-header -o name,versionName | egrep -v "samba|smbw|s3|ganesha|envoy" | tr -s " " "_"); do du -sm {data_dir}"$name" 2>&1 | grep -v  "^du:"; done'
            ],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )

    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine weka mounts on Host: {host_name}")
        else:
            data_dir_check(host_name, result)

    INFO("VERIFYING FREE SPACE FOR WEKA TRACES")
    results = parallel_execution(
        ssh_bk_hosts,
        ["df -BK /opt/weka/traces | awk 'NR==2 {print $2}' | sed s/K$//"],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine Host: {host_name} available trace space")
        else:
            weka_traces_size(host_name, result)

    if V(weka_version) <= V("4.2.1.10"):
        INFO("VERIFYING CGROUP VERSION")
        results = parallel_execution(
            ssh_bk_hosts,
            ["stat -fc %T /sys/fs/cgroup"],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to determine Host: {host_name} group version")
            else:
                cgroup_version(host_name, result)

    if V(weka_version) >= V("4.2"):
        INFO("VALIDATING CPU INSTRUCTION SET")
        results = parallel_execution(
            ssh_bk_hosts,
            ['grep "\<avx2\>" /proc/cpuinfo'],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to determine Host: {host_name} cpu instruction set")
            else:
                cpu_instruction_set(host_name, result)

    if V(weka_version) >= V("4.2.1"):
        INFO("VALIDATING IPV6")
        results = parallel_execution(
            ssh_bk_hosts,
            ["test -f /proc/net/if_inet6"],
            use_check_output=False,
            use_call=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            INFO2(f'{" " * 2}Checking IPv6 status on Host: {host_name}:')
            if result == 0:
                GOOD(f'{" " * 5}✅  IPv6 is enabled')
            else:
                BAD(
                    f'{" " * 5}❌  Cannot update to Weka version 4.3.2.x - ipv6 is disabled'
                )

    if V("4.2.6") <= V(weka_version) <= V("4.2.10"):
        INFO("VALIDATING OS KERNEL UPGRADE ELIGIBILITY")
        command = r"""
        OS=$(sudo awk -F= '/^ID=/ {gsub(/"/, "", $2); print $2}' /etc/os-release);
        if [[ $OS == rocky ]]; then
            KV=$(sudo uname -r);
            if [[ ! -z $(sudo grep "launder_folio" /usr/src/kernels/"${KV}"/include/linux/fs.h) ]]; then
                echo "P=true";
            else
                echo "P=false";
            fi;
        else
            echo "P=not_rocky";
        fi
        """
        results = parallel_execution(
            ssh_bk_hosts,
            [command],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to validate Host: {host_name} kernel version")
            else:
                check_os_kernel(host_name, result)

    INFO("VALIDATING ENDPOINT STATUS")
    command = r"""
    if sudo systemctl status falcon-sensor &> /dev/null; then
        echo "P=running"
    elif sudo lsmod | grep -q -m 1 falcon_lsm; then
        echo "P=loaded"
    else
        echo "P=not_running"
    fi
    """
    results = parallel_execution(
        ssh_bk_hosts,
        [command],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to validate Host: {host_name} endpoint status")
        else:
            endpoint_status(host_name, result)

    if V(weka_version) >= V("4.0"):
        INFO("VERIFYING BACKEND HOST PORT CONNECTIVITY STATUS")

        api_ports = []
        ips = []

        con_status = json.loads(
            subprocess.check_output(["weka", "local", "status", "-J"])
        )

        for container in con_status:
            if con_status[container]["type"] == "weka":
                api_ports.append(con_status[container]["status"]["APIPort"])
                ip = con_status[container]["resources"]["ips"]
                first_ip = ip[0]
                if first_ip not in ips:
                    ips.append(first_ip)

        curl_commands = [
            f"curl -sL --insecure https://{ips[0]}:{port} -o /dev/null; echo $? {port}"
            for port in api_ports
        ]

        results = parallel_execution(
            ssh_bk_hosts,
            curl_commands,
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to Determine Host: {host_name} port connectivity")

        host_port_connectivity(results)


def client_hosts_checks(weka_version, ssh_cl_hosts, check_version, ssh_identity):
    INFO("CHECKING PASSWORDLESS SSH CONNECTIVITY ON CLIENTS")
    ssh_cl_hosts_dict = [{"name": host} for host in ssh_cl_hosts]
    results = parallel_execution(
        ssh_cl_hosts,
        ["/bin/true"],
        use_check_output=False,
        use_call=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is not None:
            ssh_cl_hosts_dict = ssh_check(host_name, result, ssh_cl_hosts_dict)
        else:
            WARN(f'{" " * 5}⚠️  Unable to determine weka mounts on Host: {host_name}')

    ssh_cl_hosts = [host_dict["name"] for host_dict in ssh_cl_hosts_dict]
    if len(ssh_cl_hosts) == 0:
        BAD(f'{" " * 5}❌  Unable to proceed, Password SSH not configured on any host')
        sys.exit(1)

    if V(weka_version) >= V("3.12"):
        INFO("CHECKING IF OS IS SUPPORTED ON BACKENDS")
        command = r"""
        OS=$(sudo cat /etc/os-release | awk -F= '/^ID=/ {print $2}' > /dev/null);
        if [[ $OS == "centos" ]]; then
            sudo cat /etc/centos-release;
        else
                sudo cat /etc/os-release;
        fi
        """
        results = parallel_execution(
            ssh_cl_hosts,
            [command],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is not None:
                check_os_release(
                    host_name, result, weka_version, check_version, backend=True
                )
            else:
                WARN(f"Unable to determine Host: {host_name} OS version")

    if V("4.2.6") <= V(weka_version) <= V("4.2.10"):
        INFO("VALIDATING OS KERNEL UPGRADE ELIGIBILITY")
        command = r"""
        OS=$(sudo awk -F= '/^ID=/ {gsub(/"/, "", $2); print $2}' /etc/os-release);
        if [[ $OS == rocky ]]; then
            KV=$(sudo uname -r');
            if [[ ! -z $(sudo grep "launder_folio" /usr/src/kernels/"${KV}"/include/linux/fs.h) ]]; then
                echo "P=true";
            else
                echo "P=false";
            fi;
        else
            echo "P=not_rocky";
        fi
        """
        results = parallel_execution(
            ssh_cl_hosts,
            [command],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                GOOD(f"Host: {host_name} kernel validation successfull")
            else:
                check_os_kernel(host_name, result)

    INFO("CHECKING WEB CONNECTIVITY TEST ON CLIENTS")
    if len(ssh_cl_hosts) != 0:
        results = parallel_execution(
            ssh_cl_hosts,
            ['curl -sL -w "%{http_code}" "http://get.weka.io" -o /dev/null'],
            use_check_output=True,
            ssh_identity=ssh_identity,
        )
        for host_name, result in results:
            if result is None:
                WARN(f"Unable to determine weka mounts on Host: {host_name}")

        client_web_test(results)
    else:
        GOOD(f'{" " * 5}✅  Skipping clients check, no online clients found')

    INFO("CHECKING TIME DIFFERENCE ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts,
        ["date --utc +%s"],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is not None:
            time_check(host_name, result)
        else:
            WARN(f"Unable to determine Host: {host_name} weka-agent status")

    INFO("CHECKING WEKA MOUNT POINTS ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts,
        ["sudo mountpoint -qd /weka/ | wc -l"],
        use_check_output=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is not None:
            client_mount_check(host_name, result)
        else:
            WARN(f"Unable to determine wekafs mounts on client: {host_name}")

    INFO("CHECKING WEKA AGENT STATUS ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts,
        ["sudo service weka-agent status"],
        use_check_output=False,
        use_call=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is not None:
            weka_agent_check(host_name, result)
        else:
            WARN(f"Unable to determine time on Host: {host_name}")

    INFO("CHECKING WEKA CONTAINER STATUS ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts,
        ["weka local ps -J"],
        use_check_output=False,
        use_json=True,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine Host: {host_name} weka container status")

    if results != []:
        weka_container_status(results, weka_version)

    INFO("CHECKING IOMMU STATUS ON CLIENTS")
    results = parallel_execution(
        ssh_cl_hosts,
        [
            """
            iommuclass=`ls /sys/class/iommu | wc -l`
            iommugroups=`ls /sys/kernel/iommu_groups | wc -l`
            if [ $iommuclass -eq "0" ] && [ $iommugroups -eq "0" ]; then
                exit 0
            else
                exit 1
            fi
            """
        ],
        use_check_output=False,
        use_json=False,
        ssh_identity=ssh_identity,
    )
    for host_name, result in results:
        if result is None:
            WARN(f"Unable to determine Host: {host_name} IOMMU status")
        elif result.returncode == 0:
            GOOD(f'{" " * 5}✅  IOMMU is not enabled on host: {host_name}')
        else:
            WARN(f'{" " * 5}⚠️  IOMMU is enabled on host: {host_name}')


create_tar_file(log_file_path, "./weka_upgrade_checker.tar.gz")


def cluster_summary():
    INFO("CLUSTER SUMMARY:")
    GOOD(f'{" " * 5}✅  Total Checks Passed: {num_good}')
    WARN(f'{" " * 5}⚠️  Total Warnings: {num_warn}')
    BAD(f'{" " * 5}❌  Total Checks Failed: {num_bad}')


def main():
    parser = argparse.ArgumentParser(description="Weka Upgrade Checker")

    parser.add_argument(
        "-b",
        "--check-specific-backend-hosts",
        dest="check_specific_backend_hosts",
        default=False,
        nargs="+",
        help="Provide one or more ips or fqdn of hosts to check, separated by space",
    )
    parser.add_argument(
        "-d",
        "--cluster-checks-only",
        dest="cluster_checks_only",
        action="store_true",
        default=False,
        help="Will only perform cluster checks, skipping all other checks",
    )
    parser.add_argument(
        "-c",
        "--skip-client-checks",
        dest="skip_client_checks",
        action="store_true",
        default=True,
        help="Skipping all client checks",
    )
    parser.add_argument(
        "-a",
        "--run-all-checks",
        dest="run_all_checks",
        action="store_true",
        default=False,
        help="Run checks on the entire cluster, including backend hosts and client hosts",
    )
    parser.add_argument(
        "-i",
        "--ssh_identity",
        default=None,
        type=str,
        help="Path to identity file for SSH",
    )
    parser.add_argument(
        "-v",
        "--version",
        dest="version",
        action="store_true",
        default=False,
        help="weka_upgrade_check.py version info",
    )
    parser.add_argument(
        "--skip-mtu-check", action="store_true", help="Skip the MTU mismatch check."
    )

    args = parser.parse_args()

    ssh_identity = args.ssh_identity or None

    if args.version:
        print("Weka upgrade checker version: %s" % pg_version)
        sys.exit(0)

    if args.run_all_checks:
        weka_cluster_results = weka_cluster_checks(skip_mtu_check=args.skip_mtu_check)
        backend_hosts = weka_cluster_results[0]
        ssh_bk_hosts = weka_cluster_results[1]
        client_hosts = weka_cluster_results[2]
        ssh_cl_hosts = weka_cluster_results[3]
        weka_info = weka_cluster_results[4]
        weka_version = weka_info["release"]
        check_version = weka_cluster_results[5]
        backend_ips = weka_cluster_results[6]
        s3_enabled = weka_cluster_results[7]
        backend_host_checks(
            backend_hosts,
            ssh_bk_hosts,
            weka_version,
            check_version,
            backend_ips,
            ssh_identity,
            s3_enabled,
            check_rhel_systemd_hosts,
        )
        client_hosts_checks(weka_version, ssh_cl_hosts, check_version, ssh_identity)
        cluster_summary()
        INFO(f"Cluster upgrade checks complete!")
        sys.exit(0)

    elif args.cluster_checks_only:
        weka_cluster_checks(skip_mtu_check=args.skip_mtu_check)
        cluster_summary()
        INFO(f"Cluster upgrade checks complete!")
        sys.exit(0)

    elif args.check_specific_backend_hosts:
        weka_cluster_results = weka_cluster_checks(skip_mtu_check=args.skip_mtu_check)
        backend_hosts = weka_cluster_results[0]
        ssh_bk_hosts = weka_cluster_results[1]
        client_hosts = weka_cluster_results[2]
        ssh_cl_hosts = weka_cluster_results[3]
        weka_info = weka_cluster_results[4]
        weka_version = weka_info["release"]
        check_version = weka_cluster_results[5]
        backend_ips = weka_cluster_results[6]
        s3_enabled = weka_cluster_results[7]
        backend_host_checks(
            backend_hosts,
            args.check_specific_backend_hosts,
            weka_version,
            check_version,
            backend_ips,
            ssh_identity,
            s3_enabled,
            check_rhel_systemd_hosts,
        )
        cluster_summary()
        INFO(f"Cluster upgrade checks complete!")
        sys.exit(0)

    elif args.skip_client_checks:
        weka_cluster_results = weka_cluster_checks(skip_mtu_check=args.skip_mtu_check)
        backend_hosts = weka_cluster_results[0]
        ssh_bk_hosts = weka_cluster_results[1]
        client_hosts = weka_cluster_results[2]
        ssh_cl_hosts = weka_cluster_results[3]
        weka_info = weka_cluster_results[4]
        weka_version = weka_info["release"]
        check_version = weka_cluster_results[5]
        backend_ips = weka_cluster_results[6]
        s3_enabled = weka_cluster_results[7]
        backend_host_checks(
            backend_hosts,
            ssh_bk_hosts,
            weka_version,
            check_version,
            backend_ips,
            ssh_identity,
            s3_enabled,
            check_rhel_systemd_hosts,
        )
        cluster_summary()
        INFO(f"Cluster upgrade checks complete!")
        sys.exit(0)


if __name__ == "__main__":
    main()
