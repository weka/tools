#!/usr/bin/env python3

# A script runner tool to run script directory (which is bundled currently in this binary)
# To comple - whithin the ta_runner.py directory use, pyinstaller --onefile --add-data "scripts:scripts" ta_runner.py 
# (the scripts is the folder which would be included with the binary
# usage: ta_runner_darwin [-h] [--ips IPS] [--user USER] [--dzdo] [--password PASSWORD] [--password-env PASSWORD_ENV] [--password-file PASSWORD_FILE]
#                        [--key KEY] [--scripts SCRIPTS] [--log-dir LOG_DIR] [--list] [--script-num SCRIPT_NUM] [--gui] [--dialog] [--compression {gz,bz2}]
#
# Self-service remote script runner over SSH.
#
#options:
#  -h, --help            show this help message and exit
#  --ips IPS             Comma-separated list of IP addresses
#  --user USER           SSH username
#  --dzdo                Use dzdo instead of sudo for privilege escalation
#  --password PASSWORD   SSH password (same for all IPs)
#  --password-env PASSWORD_ENV
#                        Environment variable that contains SSH password
#  --password-file PASSWORD_FILE
#                        Path to file (or Unix domain socket) containing SSH password
#  --key KEY             Path to SSH private key
#  --scripts SCRIPTS     Path to local script directory
#  --log-dir LOG_DIR     Directory to store logs
#  --list                List available scripts and exit
#  --script-num SCRIPT_NUM
#                        Comma-separated list of script numbers to run (e.g. 001,005,999)
#  --gui                 Launch interactive Python GUI (questionary)
#  --dialog              Use native terminal UI (dialog with paging)
#  --compression {gz,bz2}
#                        Compression type for log archive (gz or bz2)

# General imports

import warnings 
warnings.filterwarnings(action='ignore',module='.*paramiko.*')
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import cryptography

import paramiko
from scp import SCPClient
import os
import re
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import tempfile
import encodings.idna
from dialog import Dialog
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

try:
    import questionary
except ImportError:
    questionary = None

log_dir = None

# Log bundling
def bundle_logs_to_tgz(compression_type):
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = os.path.abspath(".")
    ext = 'tgz' if compression_type == 'gz' else 'tbz2'
    bundle_name = f"ta_runner_logs_{now_str}.{ext}"
    bundle_path = os.path.join(base_dir, bundle_name)

    temp_dir = tempfile.mkdtemp()
    if os.path.isdir(log_dir):
        for f in os.listdir(log_dir):
            if f.startswith("ta_runner_") and f.endswith(".log"):
                full_path = os.path.join(log_dir, f)
                try:
                    shutil.copy(full_path, temp_dir)
                except Exception as e:
                    print(f"Could not copy log {full_path}: {e}")

    format = 'gztar' if compression_type == 'gz' else 'bztar'
    shutil.make_archive(bundle_path.replace(f".{ext}", ""), format, temp_dir)
    print(f"Logs bundled to: {bundle_path}")
    shutil.rmtree(temp_dir)

# SSH client creator
def create_ssh_client(ip, username, password=None, key_file=None):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=username, password=password, key_filename=key_file)
    return ssh

# Get password from env or user input
def get_password(args):
    if args.password:
        return args.password
    if args.password_env and args.password_env in os.environ:
        return os.environ[args.password_env]
    if args.password_file and os.path.isfile(args.password_file):
        with open(args.password_file, 'r') as f:
            return f.read().strip()
    return None

# Get the scripts list
def get_ordered_scripts(local_dir):
    files = os.listdir(local_dir)
    script_files = [f for f in files if re.match(r'^\d{1,4}[-_].*\.(sh|py)$', f)]
    script_files.sort(key=lambda f: int(re.match(r'^(\d+)', f).group(1)))
    return script_files

# Nice feature to extract script description if exists within the script
def extract_script_description(filepath):
    try:
        with open(filepath, 'r') as f:
            for _ in range(10):
                line = f.readline()
                if not line:
                    break
                match = re.search(r'DESCRIPTION\s*=\s*["\'](.+?)["\']', line)
                if match:
                    return match.group(1)
    except Exception:
        pass
    return "(no description)"

# Extract script type
def extract_script_type(filepath):
    try:
        with open(filepath, 'r') as f:
            for _ in range(10):
                line = f.readline()
                if not line:
                    break
                match = re.search(r'SCRIPT_TYPE\s*=\s*["\'](.+?)["\']', line)
                if match:
                    return match.group(1).strip().lower()
    except Exception:
        pass
    return None

# Logger
def log_local(ip, message):
    global log_dir
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"ta_runner_{ip}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] {message}\n"
    with open(log_path, "a") as f:
        f.write(full_message)

# This would show a nice dialog to choose the scripts from
def show_dialog_checklist(scripts, scripts_dir, page_size=30):
    d = Dialog(dialog="dialog")
    d.set_background_title("Select tests to Run")
    selected = set()
    total = len(scripts)
    pages = [scripts[i:i + page_size] for i in range(0, total, page_size)]
    page = 0

    while 0 <= page < len(pages):
        current_scripts = pages[page]
        menu_items = []
        for s in current_scripts:
            desc = extract_script_description(os.path.join(scripts_dir, s))
            menu_items.append((s, desc, s in selected))

        extra = len(pages) > 1

        code, tags = d.checklist(
            f"Page {page + 1} of {len(pages)} - Select scripts:",
            choices=menu_items,
            width=110,
            height=35,
            list_height=min(len(menu_items), 30),
            ok_label="Next" if page < len(pages) - 1 else "Finish",
            extra_button=extra and page > 0,
            extra_label="Back"
        )

        if code == d.OK:
            selected.update(tags)
            if page < len(pages) - 1:
                page += 1
            else:
                break
        elif code == d.EXTRA:
            page = max(0, page - 1)
        else:
            break

    return list(selected)

# Run the script per IP, would replace sudo vs dzdo if selected in command line parameters and display result
def run_on_single_ip(ip, username, password, key_file, local_dir, remote_dir, ordered_scripts, use_dzdo=False, suppress_output_if_equal=False, results_dict=None):
    print(f"Connecting to {ip}...")
    log_local(ip, f"Connecting to {ip} as {username}")
    try:
        ssh = create_ssh_client(ip, username, password, key_file)
        scp = SCPClient(ssh.get_transport())

        print(f"Copying '{local_dir}' to {ip}:{remote_dir}...")
        scp.put(local_dir, recursive=True, remote_path=remote_dir)

        sudo_cmd = "dzdo" if use_dzdo else "sudo"
        print(f"Using privilege escalation command: {sudo_cmd}")

        for script in ordered_scripts:
            remote_script = f"{remote_dir}/{script}"
            ext = os.path.splitext(script)[1]
            if ext not in ['.sh', '.py']:
                continue

            print(f"Executing {remote_script} with {'dzdo' if use_dzdo else 'sudo'}...")
            if ext == '.sh':
                cmd = f"{'dzdo' if use_dzdo else 'sudo'} bash -c 'chmod +x {remote_script} && {remote_script}'"
            elif ext == '.py':
                cmd = f"{'dzdo' if use_dzdo else 'sudo'} bash -c 'python3 {remote_script}'"

            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode()
            err = stderr.read().decode()
            result = 'PASS' if exit_status == 0 else 'FAIL'

            if suppress_output_if_equal and results_dict is not None:
                if script not in results_dict:
                    results_dict[script] = {}
                results_dict[script][ip] = result

            log_local(ip, f"Script {script} returned {result} (code {exit_status})")
            if out:
                log_local(ip, f"STDOUT:\n{out}")
                print(f"STDOUT [{script}]:\n{out}")
            if err:
                log_local(ip, f"STDERR:\n{err}")
                print(f"STDERR [{script}]:\n{err}")
            if result == 'PASS':
                colored_result = f"\033[92m{result}\033[0m"
            else:
                colored_result = f"\033[91m{result}\033[0m"
            print(f"Result for {script}: {colored_result}\n")

        print(f"Cleaning up {remote_dir} on {ip}...")
        ssh.exec_command(f"{'dzdo' if use_dzdo else 'sudo'} rm -rf {remote_dir}")

        scp.close()
        ssh.close()
        log_local(ip, f"Execution completed on {ip}")
    except Exception as e:
        error_msg = f"Failed on {ip}: {e}"
        print(error_msg)
        log_local(ip, error_msg)

# Sub function to copy and execute the script to remote machine
def copy_and_execute(ip_list, username, password=None, key_file=None, local_dir='./ta_scripts',
                     remote_dir='/tmp/ta_scripts', selected_scripts=None, limit_to_first=False, suppress_output_if_equal=False,dzdo=False):
    ordered_scripts = get_ordered_scripts(local_dir)

    if selected_scripts:
        ordered_scripts = [
            s for s in ordered_scripts
            if re.match(r'^(\d+)', s) and re.match(r'^(\d+)', s).group(1) in selected_scripts
        ]

    if limit_to_first and ip_list:
        ip_list = [ip_list[0]]

    results_dict = {} if suppress_output_if_equal else None

    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(run_on_single_ip, ip, username, password, key_file,
                            local_dir, remote_dir, ordered_scripts,
                            use_dzdo=dzdo,
                            suppress_output_if_equal=suppress_output_if_equal,
                            results_dict=results_dict)
            for ip in ip_list
        ]
        for future in as_completed(futures):
            future.result()

    if suppress_output_if_equal and results_dict:
        for script, ip_results in results_dict.items():
            result_values = set(ip_results.values())
            if len(result_values) > 1:
                print(f"\nDiscrepancy detected in script '{script}':")
                for ip, res in ip_results.items():
                    print(f"  {ip}: {res}")

# MAIN
def main():
    global log_dir
    parser = argparse.ArgumentParser(description='Self-service remote script runner over SSH.')
    parser.add_argument('--ips', help='Comma-separated list of IP addresses')
    parser.add_argument('--user', help='SSH username')
    parser.add_argument('--dzdo', action='store_true', help='Use dzdo instead of sudo for privilege escalation')
    parser.add_argument('--password', help='SSH password (same for all IPs)')
    parser.add_argument('--password-env', help='Environment variable that contains SSH password')
    parser.add_argument('--password-file', help='Path to file (or Unix domain socket) containing SSH password')
    parser.add_argument('--key', help='Path to SSH private key')
    parser.add_argument('--scripts', default=get_resource_path('scripts'), help='Path to local script directory')
    parser.add_argument('--log-dir', default=os.path.expanduser("~/ta_runner_logs"), help='Directory to store logs')
    parser.add_argument('--list', action='store_true', help='List available scripts and exit')
    parser.add_argument('--script-num', help='Comma-separated list of script numbers to run (e.g. 001,005,999)')
    parser.add_argument('--gui', action='store_true', help='Launch interactive Python GUI (questionary)')
    parser.add_argument('--dialog', action='store_true', help='Use native terminal UI (dialog with paging)')
    parser.add_argument('--compression', choices=['gz', 'bz2'], default='gz', help='Compression type for log archive (gz or bz2)')

    args = parser.parse_args()
    log_dir = args.log_dir
    password = get_password(args)

    all_scripts = get_ordered_scripts(args.scripts)

    if args.list:
        for s in all_scripts:
            path = os.path.join(args.scripts, s)
            desc = extract_script_description(path)
            print(f"{s}: {desc}")
        return

    selected_scripts = None

    if args.script_num:
        selected_scripts = [s.strip().zfill(3) for s in args.script_num.split(',')]

    elif args.dialog:
        if not shutil.which('dialog'):
            args.gui = True
        else:
            selections = show_dialog_checklist(all_scripts, args.scripts)
            if not selections:
                print("No scripts selected. Exiting.")
                return
            else:
                selected_scripts = [re.match(r'^(\d+)', s).group(1) for s in selections if re.match(r'^(\d+)', s)]

    if args.gui:
        if not questionary:
            print("questionary not installed. Run: pip install questionary")
            return
        choices = [
            questionary.Choice(
                title=f"{s}: {extract_script_description(os.path.join(args.scripts, s))}",
                value=s
            ) for s in all_scripts
        ]
        selections = questionary.checkbox("Select scripts to run:", choices=choices).ask()
        if not selections:
            return
        selected_scripts = [re.match(r'^(\d+)', c).group(1) for c in selections]

    if not args.ips or not args.user or (not password and not args.key):
        print("Missing required arguments. Run with -h for help.")
        return

    ip_list = [ip.strip() for ip in args.ips.split(',')]

    is_single_type = False
    is_parallel_compare = False
    for s in all_scripts:
        script_number = re.match(r'^(\d+)', s)
        if script_number and (not selected_scripts or script_number.group(1) in selected_scripts):
            path = os.path.join(args.scripts, s)
            script_type = extract_script_type(path)
            if script_type == "single":
                is_single_type = True
            if script_type == "parallel-compare-backends":
                is_parallel_compare = True

    if is_single_type and ip_list:
        print("SCRIPT_TYPE=single detected. Running only on the first IP:", ip_list[0])

    copy_and_execute(
        ip_list=ip_list,
        username=args.user,
        password=password,
        key_file=args.key,
        local_dir=args.scripts,
        selected_scripts=selected_scripts,
        dzdo=args.dzdo,
        limit_to_first=is_single_type,
        suppress_output_if_equal=is_parallel_compare
    )

    bundle_logs_to_tgz(args.compression)

if __name__ == "__main__":
    main()

