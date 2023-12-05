import json
import time
import subprocess
import requests
from requests.packages import urllib3
from src.common import bcolors, global_vars, Automode
import re
import argparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_s3_hosts(hosts=None):
    if not hosts:
        hosts = []
        output = send_bash_command("weka s3 cluster status")
        hosts_id = re.findall(r'\d+', output.decode("utf-8"))
        for hid in hosts_id:
            output = send_bash_command(f"weka cluster host {hid} --no-header -o hostname")
            hosts.append(output.decode("utf-8").rstrip('\n'))
    return hosts


def get_host_ids(hosts):
    output = send_bash_command("weka cluster containers -J")
    containers = json.loads(output.decode("utf-8"))
    for container in containers:
        if container['hostname'] in hosts:
            id = int(''.join(filter(str.isdigit, container['host_id'])))
            global_vars.s3_hosts[container['hostname']] = id


def get_fe_container_name():
    output = send_bash_command(f"sudo weka local exec -C s3 cat /data/container/specific_resources.json")
    configs = json.loads(output.decode("utf-8"))
    return configs['s3_options']['container_name']


def get_arguments():
    parser = argparse.ArgumentParser(prog='ETCD to KWAS Migration')
    parser.add_argument('-a', '--auto-mode', type=int, default=1, help='Automated Level [0-2] where 0 is manual mode. '
                                                                       'default is 1 (semi-automated)')
    parser.add_argument('-s', '--hosts', type=str, nargs='+', help="S3 hosts in cluster (this field is mandatory in manual mode)")
    parser.add_argument('-f', '--frontend-container-name', type=str, help="S3 manager container name (this field is mandatory in manual mode)")
    parser.add_argument('-t', '--skip-checks', default=False, action='store_true', help="Skip preliminary checks")

    args = parser.parse_args()
    return args


def set_args(args):
    global_vars.auto_mode = args.auto_mode
    if global_vars.auto_mode == Automode.MANUAL.value and not args.hosts:
        print(f"{bcolors.RED}ERROR: In manual mode user must pass hosts as args.{bcolors.ENDC}")
        exit(1)

    if global_vars.auto_mode == Automode.MANUAL.value and not args.frontend_container_name:
        print(f"{bcolors.RED}ERROR: In manual mode user must pass mngmt container name as args.{bcolors.ENDC}")
        exit(1)

    hosts = args.hosts if args.hosts else get_s3_hosts()
    get_host_ids(hosts)
    container_name = args.frontend_container_name if args.frontend_container_name else get_fe_container_name()
    global_vars.socket_path = global_vars.socket_prefix + container_name + global_vars.socket_extension
    global_vars.skip_checks = args.skip_checks
    global_vars.migrate_host = list(global_vars.s3_hosts.keys())[0]
    global_vars.migrate_host_id = global_vars.s3_hosts[global_vars.migrate_host]
    auto_mode_strs = ['manual', 'semi-automated', 'fully automated']
    print(f"{bcolors.CYAN}Set migration options to: {auto_mode_strs[global_vars.auto_mode]} migration on hosts: "
          f"{global_vars.s3_hosts.keys()} using socket path: {global_vars.socket_path} {bcolors.ENDC}")


def set_drain_mode(enable, host_num):
    if enable:
        cmd = f"weka debug manhole --slot 0 --host {host_num} s3_enter_drain_mode"
    else:
        cmd = f"weka debug manhole --slot 0 --host {host_num} s3_exit_drain_mode"
    output = send_bash_command(cmd)


def wait_for_drain(host):
    while is_host_ready(global_vars.s3_hosts[host]):
        time.sleep(0.5)
    time.sleep(10)
    while True:
        r = send_request(f"http://{host}:9001/minio/drain/status")
        data = r.json()
        if data["mode"] == "true" and data["progress"] == "100":
            break
        time.sleep(0.5)


def get_migration_status(host):
    return send_request(f"http://{host}:9001/minio/migration/migrate/kwas").json()


def print_errors_dict(err_dict):
    for key, values in err_dict.items():
        print(f"{bcolors.BOLD}{key}:{bcolors.ENDC}")
        if isinstance(values, list):
            for err in values:
                print(f"\t{err}")
        else:
            print(f"\t{err}")


def send_bash_command(cmd):
    process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()
    if error:
        print(f"{bcolors.RED}ERROR: Failed to run command '{cmd}' Fix what is needed and rerun script{bcolors.ENDC}")
        exit(1)
    return output


def send_request(cmd, body=None):
    if body:
        r = requests.put(cmd, json=body, verify=False)
    else:
        r = requests.get(cmd, verify=False)
    if r.status_code != 200:
        try:
            r.json()
            print(f"{bcolors.RED}ERROR: Request failed due to: {r['error']}{bcolors.ENDC}")
        except Exception as e:
            print(f"{bcolors.RED}ERROR: Couldn't communicate with minIO{bcolors.ENDC}")
        finally:
            exit(1)
    return r


def continue_to_next_step():
    while True:
        response = input(
            f"{bcolors.BLUE}\tDo you want to proceed? (c)ontinue, (e)xit or (r)evert back to etcd: {bcolors.ENDC}")
        if response.lower() == 'c':
            return True
        elif response.lower() == 'e':
            print(
                f"{bcolors.YELLOW}WARNING: Exiting script, leaving system as it is now.{bcolors.ENDC}")
            exit(1)
        elif response.lower() == 'r':
            return False
        else:
            print(f"{bcolors.YELLOW}Invalid input. Please type c/e/r{bcolors.ENDC}")


def continue_to_next_host():
    while True:
        response = input(
            f"{bcolors.BLUE}\tProceed to next host? (y)es (r)evert: {bcolors.ENDC}")
        if response.lower() == 'y':
            return True
        elif response.lower() == 'r':
            return False
        else:
            print(f"{bcolors.YELLOW}Invalid input. Please type y/r{bcolors.ENDC}")


def validate_host_in_migration_read_only_mode(host, set):
    r = send_request(f"http://{host}:9001/minio/migration/ro-mode")
    response_body = r.json()
    expected_value = "true" if set else "false"
    if response_body["Mode"] != expected_value:
        return False
    return True


def validate_set_migration_read_only_mode(set):
    for host in global_vars.s3_hosts.keys():
        if not validate_host_in_migration_read_only_mode(host, set):
            expected_error = "enter" if set else "exit"
            print(
                f"{bcolors.RED}ERROR: Host {host} failed to {expected_error} Migration Read Only Mode. Fix what is needed and rerun script{bcolors.ENDC}")
            exit(1)


def is_client_running_on_host(client_str, host):
    r = send_request(f"http://{host}:9001/minio/migration/clients")
    response_body = r.json()
    disable_client = 'etcd' if client_str == 'kwas' else 'kwas'
    return response_body[f'{client_str} client'] == "true" and response_body[f'{disable_client} client'] == "false"


def is_etcd_up_and_working():
    for host in global_vars.s3_hosts.keys():
        output = send_bash_command(f"ssh {host} grep -r 'Unable to initialize IAM sub-system' /opt/weka/logs/s3/minio.log* | wc -l")
        if output != b"0\n":
            print(f"{bcolors.RED}ERROR: Host {host} minIO failed to load all ETCD data. Fix what is needed and re-run script{bcolors.ENDC}")
            exit(1)
    return True


def is_host_ready(host_id):
    output = send_bash_command("weka s3 cluster status -J")
    hosts_health = json.loads(output)
    return hosts_health[f'HostId<{host_id}>']
