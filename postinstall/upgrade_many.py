#!/usr/bin/env python2.7

import argparse
import subprocess
import json
import time
import sys
import os
# from pprint import pprint
from datetime import datetime
from os.path import exists
SSH_OPTIONS = ["ssh", "-o", "LogLevel=ERROR", "-o", "UserKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=no"]

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

def get_timestamp_prefix():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print("%s LOG: %s" % (get_timestamp_prefix(), msg))

def prompt_user_input():
    # Portable python2/3 input
    try:
        get_input = raw_input
    except NameError:
        get_input = input

    return get_input().strip().lower()


def is_fully_protected(status, rebuild_status, print_rebuild_status=True):
    if rebuild_status["unavailableMiB"] != 0:
        if print_rebuild_status:
            subprocess.call(["weka", "status", "rebuild"])
            log("Cluster has too many failures (status %s) (seen rebuilding cluster, as expected)" % (status["status"],))
        return False

    if any(prot["MiB"] != 0 for prot in rebuild_status["protectionState"][1:]) or rebuild_status["protectionState"][0] == 0:
        if print_rebuild_status:
            subprocess.call(["weka", "status", "rebuild"])
            scrubber_rate = json.loads(subprocess.check_output(["weka", "debug", "config", "show", "clusterInfo.scrubberBytesPerSecLimit", "-J"]))
            log("Rebuilding at rate of %sMiB/sec (scrubber rate)" % (scrubber_rate / (1 << 20),));
            log("Still has failures (status %s)" % (status["status"],))
        return False

    subprocess.call(["weka", "status", "rebuild"])
    log("Cluster is fully protected (status %s)" % (status["status"],))
    return True


def wait_for_unhealthy_cluster():
    status_max_retries = 180
    attempts = 0
    while True:
        time.sleep(1)
        attempts += 1

        try:
            rebuild_status = json.loads(subprocess.check_output(["weka", "status", "rebuild", "-J"]))
            status = json.loads(subprocess.check_output(["weka", "status", "-J"]))

            should_print = attempts % 3 == 0 # Only print in some of the iterations
            if not is_fully_protected(status, rebuild_status, print_rebuild_status=should_print):
                log("Seen rebuilding cluster, as expected (status %s)" % (status["status"],))
                return

        except subprocess.CalledProcessError:
            if attempts >= status_max_retries:
                log("Exhausted retries when querying cluster's rebuild status")
                sys.exit(1)

            log("Error querying cluster's rebuild status, retrying")
            continue

        log("Cluster is unhealthy (status %s)" % (status["status"],))


def wait_for_healthy_cluster(print_healthy=True):
    status_max_retries = 180
    attempts = 0
    wait_start = datetime.now()
    while True:
        attempts += 1
        if attempts > 1:
            time.sleep(1)

        try:
            status = json.loads(subprocess.check_output(["weka", "status", "-J"]))
            rebuild_status = json.loads(subprocess.check_output(["weka", "status", "rebuild", "-J"]))

            should_print = attempts % 5 == 0 # Only print in some of the iterations
            if not is_fully_protected(status, rebuild_status, print_rebuild_status=should_print):
                continue

        except subprocess.CalledProcessError:
            if attempts >= status_max_retries:
                log("Exhausted retries when querying cluster's rebuild status")
                sys.exit(1)

            log("Error querying cluster's rebuild status, retrying")
            continue

        def check_active_equals_total(json):
            return json["active"] == json["total"]

        if not check_active_equals_total(status["drives"]):
            log("Not all drives are active")
            continue
        if not check_active_equals_total(status["io_nodes"]):
            log("Not all io nodes are active")
            continue
        if not check_active_equals_total(status["hosts"]["backends"]):
            log("Not all backend hosts are active")
            continue
        if not check_active_equals_total(status["buckets"]):
            log("Not all backend buckets are up")
            continue

        if print_healthy:
            wait_end = datetime.now()
            wait_delta = wait_end - wait_start
            log(" === Cluster is healthy (status %s, took %s seconds) ===" % (status["status"], wait_delta.total_seconds(), ))

        break


def upgrade_flow(target_version, ssh_identity=None, container_name=None, skip_health_checks=False, skip_prepare_upgrade=False, skip_local_start=False):
    # TODO: Ask the user if we distributed the version

    timestamp = get_timestamp()
    container_filter = ["-F", "container="+container_name] if container_name is not None else []
    hosts = json.loads(subprocess.check_output(["weka", "cluster", "host", "-b", "-J"] + container_filter))

    if container_name is None:
        container_name = "default"

    upgrade_all_already_checked = False
    skipped_hosts = 0
    upgraded_hosts = 0
    for host in hosts:
        ip = host["host_ip"]
        port = host["mgmt_port"]
        is_up = host["status"] == "UP"
        hostname = host["hostname"]
        log("Querying %s at %s..." % (hostname, ip))
        source_version = ""
        if is_up:
            machine_info = json.loads(subprocess.check_output(["weka", "debug", "jrpc", "-H", ip, "-P", str(port), "client_query_backend"]))
            source_version = machine_info['software_release']
        else:
            source_version = host["sw_release_string"]
        log("Queried %s: currently running %s" % (hostname, source_version))

        if source_version == target_version:
            log("No need to upgrade %s, it is already running %s" % (hostname, source_version))
            skipped_hosts += 1
            continue
        if not skip_health_checks:
            wait_for_healthy_cluster(print_healthy=False)

        if not upgrade_all_already_checked:
            log("Upgrade %s to %s? [y]es / [s]kip / all> " % (hostname, target_version, ))
            i = prompt_user_input()
            if i in ("s", "skip"):
                log("Skipping %s" % (hostname, ))
                skipped_hosts += 1
                continue

            if i in ("all", ):
                log("Will upgrade %s and then continue to upgrade ALL of the cluster" % (hostname, ))
                upgrade_all_already_checked = True
            elif i not in ("y", "yes"):
                log("Unacceptable input '%s', quitting" % (i, ))
                sys.exit(1)

        is_root = os.geteuid() == 0

        should_sudo = not is_root

        ssh_identity_args = ["-i", ssh_identity] if ssh_identity is not None else []
        sudo_args = ["sudo"] if should_sudo else []
        ssh_opts = SSH_OPTIONS + ssh_identity_args + [ip] + sudo_args

        def ssh_args(args): return ssh_opts + list(args)

        def ssh_call(*args):
            log("Running '%s' on %s via ssh" % (' '.join(str(x) for x in args), ip))
            subprocess.check_call(ssh_args(args))

        def ssh_unchecked_call(*args):
            log("Running '%s' on %s via ssh (allow failure)" % (' '.join(str(x) for x in args), ip))
            subprocess.call(ssh_args(args))

        wait_start = datetime.now()

        # This yields incorrect versions in MBC, when each container runs different versions
        # remote_old_version = subprocess.check_output(ssh_args(["weka", "version", "current"])).strip().decode("utf8")

        assert source_version != target_version, "We tested that it is NOT the target version but 'weka version' says it is?!"
        log("Starting upgrade of %s from %s to %s" % (hostname, source_version, target_version, ))

        ## We assume we delivered the version to every host already
        log("weka version get %s" % (target_version,))
        ssh_call("weka", "version", "get", target_version)
        if skip_prepare_upgrade:
            log("Skipping preparation of driver for upgrade on %s" % (hostname,))
        else:
            log("Preparing driver for upgrade on %s" % (hostname,))
            if exists("/proc/wekafs/interface"):
                ssh_call("echo", "prepare-upgrade", ">", "/proc/wekafs/interface")
            ssh_call("sync")

        log("Preparing version on %s using 'weka version prepare %s'" % (hostname, target_version, ))
        ssh_call("weka", "version", "prepare", target_version)

        log("Stopping local containers on %s" % (hostname,))
        try:
            ssh_call("weka", "local", "stop", container_name, "--force")
        except subprocess.CalledProcessError as e:
            ssh_call("weka", "local", "stop", container_name)

        # Allowed to fail:
        log("Moving target version data dir on %s, if one exists:" % (hostname, ))
        ssh_unchecked_call("mv",
                           "/opt/weka/data/%s_%s" % (container_name, target_version,),
                           "/opt/weka/data/%s_%s.bk.%s" % (container_name, target_version, timestamp))

        log("Moving old data dir to target data dir")
        try:
            ssh_call("mv",
                     "/opt/weka/data/%s_%s" % (container_name, source_version,),
                     "/opt/weka/data/%s_%s" % (container_name, target_version,))
        except Exception:
            log("Failed to move the data dir to target version, starting back up and bailing out...")
            ssh_call("weka", "local", "start", container_name,)
            raise

        if container_name == 'default':
            ssh_unchecked_call("weka", "version", "set", target_version,)
        else:
            ssh_unchecked_call("weka", "version", "set", target_version, "-C", container_name,)
        if skip_local_start:
            log("NOT starting containers on %s because --skip-local-start" % (hostname,))
        else:
            try:
                log("Starting containers on %s" % (hostname,))
                ssh_call("weka", "local", "start", container_name, )
                log("Started containers on %s" % (hostname,))
            except Exception:
                log("Failed to weka version start, renaming back, starting back up and bailing out...")
                ssh_call("mv",
                         "/opt/weka/data/%s_%s" % (container_name, target_version,),
                         "/opt/weka/data/%s_%s" % (container_name, source_version,))
                if container_name == 'default':
                    ssh_unchecked_call(("weka", "version", "set", source_version,))
                else:
                    ssh_unchecked_call("weka", "version", "set", source_version, "-C", container_name, )

                if not skip_local_start:
                    ssh_call("weka", "local", "start", container_name,)
                raise


        upgraded_hosts += 1
        if not skip_health_checks:
        # We first want to see the cluster as unhealthy before we wait for it to become healthy
            wait_for_unhealthy_cluster()
            wait_for_healthy_cluster()

        wait_end = datetime.now()
        wait_delta = wait_end - wait_start
        log(" === Finished upgrade of %s, %s container from %s to %s (took %s seconds) ===" % (
            hostname, container_name, source_version, target_version, wait_delta.total_seconds(), ))

    return upgraded_hosts, skipped_hosts


def main():
    parser = argparse.ArgumentParser(description='Rolling-upgrade multiple hosts via ssh')
    parser.add_argument('target_version', type=str, help='The target version')
    parser.add_argument('-i', dest='ssh_identity', type=str, help='SSH identity to pass to ssh -i')
    parser.add_argument('-c', dest='container_name', type=str, help='in order to rolling upgrade just one container')
    parser.add_argument('-s', dest='skip_health_checks', type=bool, default=False,
                        help='WARNING: DON\'T USE THIS OPTION UNLESS YOU REALLY NEED TO. '
                             'if cluster is unhealthy, don\'t wait for rebuilds, and health checks')
    parser.add_argument('--skip-prepare-upgrade', dest='skip_prepare_upgrade', type=bool, default=False,
                        help='Do not ask the driver to prepare for the upgrade and wait for in-flight ops')
    parser.add_argument('--skip-local-start', dest='skip_local_start', type=bool, default=False,
                        help='Do not "weka local start" in the new version')


    args = parser.parse_args()
    upgrade(args.target_version, args.ssh_identity, args.container_name, args.skip_health_checks, args.skip_prepare_upgrade, args.skip_local_start)

def upgrade(target_version, ssh_identity=None, container_name=None, skip_health_checks=False, skip_prepare_upgrade=False, skip_local_start=False):
    wait_start = datetime.now()
    upgraded_hosts, skipped_hosts = upgrade_flow(target_version, ssh_identity, container_name, skip_health_checks, skip_prepare_upgrade, skip_local_start)

    wait_end = datetime.now()
    wait_delta = wait_end - wait_start
    log(" === Upgrade to %s has finished (%s upgraded, %s skipped, took %s seconds) ===" % (
        target_version, upgraded_hosts, skipped_hosts, wait_delta.total_seconds(), ))

if __name__ == '__main__':
    main()
