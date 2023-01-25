#!/usr/bin/env python2.7

import argparse
import re
import subprocess
import json
import time
import sys
import os
import shlex
# from pprint import pprint
from datetime import datetime

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


def wait_for_unhealthy_cluster(timeout_secs=120):
    status_max_retries = 180
    attempts = 0
    start = time.time()
    while True:
        time.sleep(1)
        attempts += 1

        try:
            if time.time() - start >= timeout_secs:
                log("Timed out waiting for the cluster to become unhealthy - Assuming it's healthy")
                return

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

        if print_healthy:
            wait_end = datetime.now()
            wait_delta = wait_end - wait_start
            log(" === Cluster is healthy (status %s, took %s seconds) ===" % (status["status"], wait_delta.total_seconds(), ))

        break

def parse_typed_id(typed_id):
    typed_id_str = str(typed_id)
    value = typed_id_str[typed_id_str.find('<')+1:-1]
    if value == 'INVALID':
        return None
    return int(value)

class Host:
    def __init__(self, host_json):
        self.typed_id = str(host_json["host_id"])
        self.id = re.search("HostId<(\\d+)>", self.typed_id).group(1)
        self.ip = str(host_json["host_ip"])
        self.port = str(host_json["mgmt_port"])
        self.hostname = str(host_json["hostname"])
        self.is_up = host_json["status"] == "UP"
        self.failure_domain_id = parse_typed_id(host_json["failure_domain_id"])
        self.failure_domain_type = host_json["failure_domain_type"]
        self.failure_domain_name = host_json["failure_domain"]
        self.sw_release_string = str(host_json["sw_release_string"])

        self.ssh_identity_args = []
        is_root = os.geteuid() == 0
        should_sudo = not is_root
        self.ssh_sudo_args = ["sudo"] if should_sudo else []

    def set_identity_args(self, identity_args):
        self.ssh_identity_args = identity_args

    def ssh_args(self, args):
        ssh_opts = SSH_OPTIONS + self.ssh_identity_args + [self.ip] + self.ssh_sudo_args
        return ssh_opts + list(args)

    def ssh_call(self, *args):
        log("Running '%s' on %s (%s) via ssh" % (' '.join(str(x) for x in args), self.hostname, self.ip))
        subprocess.check_call(self.ssh_args(args))

    def ssh_call_with_output(self, *args):
        log("Running '%s' on %s (%s) via ssh, capturing output" % (' '.join(str(x) for x in args), self.hostname, self.ip))
        return subprocess.check_output(self.ssh_args(args))

    def ssh_unchecked_call(self, *args):
        log("Running '%s' on %s (%s) via ssh (allow failure)" % (' '.join(str(x) for x in args), self.hostname, self.ip))
        subprocess.call(self.ssh_args(args))


def _s3_cluster_status():
    return json.loads(subprocess.check_output(['weka', 's3', 'cluster', 'status', '-J']))


def is_s3_host(host):
    return host.typed_id in _s3_cluster_status()


def wait_for_s3_cluster_to_be_ready(host):
    while True:
        try:
            log("Fetching S3 cluster status")
            s3_cluster_status = _s3_cluster_status()
            if not s3_cluster_status[host.typed_id]:
                log("Host %s's S3 container appears to be down" % (host.hostname,)),
                if is_minio_in_drain_mode(host):
                    log("But minio is up and in drain mode, so undraining and making sure it's still up")
                    s3_undrain(host)
                    continue
            if all(s3_cluster_status.values()):
                log("All S3 containers in the cluster are ready, Checking etcd's health...")
                if is_etcd_up(host):
                    log("etcd is healthy as well")
                    break
                log("etcd is not healthy yet")
        except Exception as e:
            log("Caught exception waiting for S3 to become ready: %s" % str(e))
            continue

        time.sleep(1)

    log("S3 cluster status: %s" % (str(s3_cluster_status)))


def is_minio_in_drain_mode(host):
    s3_cluster_status = json.loads(subprocess.check_output(["weka", "s3", "cluster", "-J"]))
    protocol = "https" if s3_cluster_status["tls_enabled"] else "http"
    port = str(s3_cluster_status["port"])
    drain_url = protocol + "://127.0.0.1:" + port + "/minio/drain/mode"
    minio_drain_check_cmd = ["weka", "local", "exec", "-C", "s3", "--", "curl", "-sk", drain_url]
    drain_status = json.loads(host.ssh_call_with_output(*minio_drain_check_cmd))
    return json.loads(drain_status["mode"])


def s3_has_active_ios(host):
    cmd = ['weka', 'debug', 'jrpc', 'container_get_drain_status', 'hostId=%s' % host.id]
    return not json.loads(subprocess.check_output(cmd))


def s3_undrain(host):
    def undrain():
        try:
            log("Starting S3 container undrain on %s" % (host.hostname,))
            subprocess.check_output(["weka", "s3", "cluster", "undrain", host.id])
            log("Started S3 container undrain on %s" % (host.hostname,))

        except:
            log("retrying S3 undrain on %s" % (host.hostname,))
            time.sleep(3)
            undrain()
    undrain()


def s3_start_and_undrain(host):
    log("Starting S3 container on %s" % (host.hostname,))
    host.ssh_call("weka", "local", "start", "s3")
    log("Started S3 container on %s" % (host.hostname,))
    s3_undrain(host)



def s3_wait_for_drain(host, grace_period, drain_timeout, interval, required_checks, force_stop_s3_with_failed_drain_check=False):
    log("Starting to wait for a grace period of %ss before polling drain status" % grace_period)
    time.sleep(grace_period)
    log("Grace period finished, starting to poll drain status")
    start = time.time()
    successful_checks_in_a_row = 0

    while time.time() - start < drain_timeout:
        try:
            minio_in_drain_mode = is_minio_in_drain_mode(host)
            has_active_ios = s3_has_active_ios(host)
            if minio_in_drain_mode and not has_active_ios:
                successful_checks_in_a_row += 1
                log("Got %s successful drain checks in a row on host %s; We need %s"
                    % (successful_checks_in_a_row, host.hostname, required_checks))
                if successful_checks_in_a_row >= required_checks:
                    log("Got %s successful drain checks in a row on host %s, drain is considered finished"
                        % (successful_checks_in_a_row, host.hostname))
                    return
            else:
                log("Drain on host %s hasn't finished yet. Is Minio in drain mode? %s. Are there active IOs? %s."
                    % (host.hostname, minio_in_drain_mode, has_active_ios))
                successful_checks_in_a_row = 0
            time.sleep(interval)
        except Exception as e:
            log("Error while waiting for draining S3 container of %s to finish: '%s'; retrying" % (host.hostname, e))
            successful_checks_in_a_row = 0

    # If we timed-out waiting for IOs to complete, and IOs haven't completed, we will ask the user whether it makes sense to continue or not
    # if not upgrade_all_already_checked:
    log("")
    log("Following the drain grace period (%s seconds), we waited %s seconds for IOs to complete, but IOs seem to continue running"
        % (grace_period, drain_timeout))
    log("At this point we can either continue and stop S3 on %s (This is safe only if the clients will retry properly through another S3 server), or Exit"
        % (host.hostname, ))

    if force_stop_s3_with_failed_drain_check:
        log("User selected force flag, so we will stop S3 container even though drain check failed")
        return

    log("Typing Yes now will force stop S3 container on %s" % (host.hostname, ))
    log("Typing No now will exit the script and S3 on %s will still be in drain mode (use `weka s3 cluster undrain` to undrain explicitly)"
        % (host.hostname, ))
    log("Continue to stop S3 on %s? [y]es / [n]o> " % (host.hostname, ))
    i = prompt_user_input()
    if i in ("y", "yes"):
        log("User allows stopping S3 on %s" % (host.hostname, ))
        return

    raise Exception("Timed out waiting for draining S3 container of %s to finish" % host.hostname)


def s3_drain(host, grace_period, drain_timeout, interval, required_checks, force_stop_s3_with_failed_drain_check=False):
    log("Waiting for S3 cluster to be ready before draining")
    wait_for_s3_cluster_to_be_ready(host)

    log("S3 container is ready on host %s" % (host.hostname,))

    start = time.time()
    log("Starting drain of S3 container on %s" % (host.hostname,))
    subprocess.check_output(['weka', 's3', 'cluster', 'drain', host.id])
    log("Started drain of S3 container on %s" % (host.hostname,))

    log("Waiting for S3 container %s to finish draining" % (host.hostname,))
    s3_wait_for_drain(host, grace_period, drain_timeout, interval, required_checks, force_stop_s3_with_failed_drain_check)
    log("Finished draining S3 container %s in %.2fs" % (host.hostname, time.time() - start))


def is_etcd_up(host):
    cmd = ["weka", "local", "exec", "-C", "s3", "etcdctl", "endpoint", "health", "--cluster", "-w", "json"]
    statuses = json.loads(host.ssh_call_with_output(*cmd))

    for status in statuses:
        if not status["health"]:
            log("   etcd member on %s is down" % status["endpoint"])

    return all(status["health"] for status in statuses)


def wait_for_container_readiness(host, timeout_secs=180):
    start = time.time()

    while True:
        try:
            if time.time() - start >= timeout_secs:
                raise Exception("Timed out waiting for the container to become READY on %s" % host.hostname)

            local_status = json.loads(host.ssh_call_with_output(*shlex.split("weka local status -J")))
            state = str(local_status['default']['internalStatus']['state'].decode('utf-8'))
            if state == 'READY':
                log("Container on %s is now ready" % (host.hostname))
                return

            log("Current container state on %s: %s" % (host.hostname, state))
            time.sleep(1)

        except subprocess.CalledProcessError:
            log("Error querying the container's state, retrying")
            time.sleep(1)
            continue


def change_failure_domains(s3_drain_timeout, s3_drain_grace, s3_drain_interval, s3_drain_required_checks, force_stop_s3_with_failed_drain_check=False, ssh_identity=None, container_name=None, skip_health_checks=False, skip_prepare_upgrade=False, skip_local_start=False, skip_local_disable=False, wait_unhealthy_timeout_secs=None, skip_s3_drain=False):
    timestamp = get_timestamp()
    container_filter = ["-F", "container="+container_name] if container_name is not None else []
    hosts = [Host(host_json) for host_json in json.loads(subprocess.check_output(["weka", "cluster", "host", "-b", "-J"] + container_filter))]

    passed_explicit_container_name = container_name is not None
    if container_name is None:
        container_name = "default"

    change_all_already_checked = False
    skipped_hosts = 0
    changed_hosts = 0
    for host in hosts:
        host.set_identity_args(["-i", ssh_identity] if ssh_identity is not None else [])

        log("Queried %s: currently running with failure domain type %s (id: %s, name=%s)" % (
            host.hostname, host.failure_domain_type, host.failure_domain_id, host.failure_domain_name))

        if host.failure_domain_type == "USER":
            log("No need to change %s, it already has manual failure domain called %s" % (host.hostname, host.failure_domain_name))
            skipped_hosts += 1
            continue

        if not skip_health_checks:
            wait_for_healthy_cluster(print_healthy=False)

        if not change_all_already_checked:
            log("Change %s:%s failure domain to manual? [y]es / [s]kip / all> " % (host.hostname, container_name, ))
            i = prompt_user_input()
            if i in ("s", "skip"):
                log("Skipping %s" % (host.hostname, ))
                skipped_hosts += 1
                continue

            if i in ("all", ):
                log("Will change %s and then continue to change ALL of the cluster's failure domains" % (host.hostname, ))
                change_all_already_checked = True
            elif i not in ("y", "yes"):
                log("Unacceptable input '%s', quitting" % (i, ))
                sys.exit(1)

        is_s3 = is_s3_host(host)
        if is_s3:
            log("Container %s:%s is an S3 container. Checking etcd status..." % (host.hostname, container_name))
            if not is_etcd_up(host):
                raise Exception("etcd is not healthy, aborting upgrade")

        wait_start = datetime.now()

        log("Failure domain ID of %s:%s is currently %s (type=%s)" % (host.hostname, container_name, host.failure_domain_id, host.failure_domain_type))
        if host.failure_domain_id is None:
            raise Exception("Failure domain ID of host %s is None, but it should be a valid integer!")

        new_failure_domain_name = 'FD_%d' % host.failure_domain_id
        log("New failure domain selected for %s:%s is %s (based on ID %s)" % (host.hostname, container_name, new_failure_domain_name, host.failure_domain_id))

        if is_s3 and not skip_s3_drain:
            s3_drain(host, s3_drain_grace, s3_drain_timeout, s3_drain_interval, s3_drain_required_checks, force_stop_s3_with_failed_drain_check)

            log("Stopping S3 container on host %s (it might take some time, and a warning might be displayed)" % (host.hostname,))
            host.ssh_call("weka", "local", "stop", "s3")
            log("Stopped S3 container on host %s" % (host.hostname,))

        log("Changing of failure-domain on %s to %s" % (host.hostname, new_failure_domain_name))
        host.ssh_call("weka", "local", "resources", "failure-domain", "--name", new_failure_domain_name)

        log("Applying resources %s" % (host.hostname, ))
        host.ssh_call("weka", "local", "resources", "apply", "-f")

        log("Waiting for container to become ready on %s" % (host.hostname, ))
        wait_for_container_readiness(host)

        log("Getting host-id from the current container on %s" % (host.hostname, ))
        host_id = json.loads(host.ssh_call_with_output(*shlex.split("weka debug manhole -s 0 getServerInfo")))["hostIdValue"]

        log("Waiting for host with %s to become UP in 'weka cluster host'" % (host.hostname, ))
        host_entry = None
        while True:
            try:
                host_entry = json.loads(host.ssh_call_with_output(*shlex.split("weka cluster host -J -F id=%s" % host_id)))[0]
                host_status = str(host_entry['status'].decode('utf-8'))
                if host_status == "UP":
                    break

                log("Host %s (with id %s) is currently %s" % (host.hostname, host_id, host_status))
                time.sleep(1)

            except Exception as e:
                log("Error getting host information from cluster's hosts list")
                time.sleep(1)

        last_failure = str(host_entry['last_failure'].decode('utf-8'))
        failure_domain_from_hosts_list = str(host_entry['failure_domain'].decode('utf-8'))
        if str(host_entry['failure_domain'].decode('utf-8')) != new_failure_domain_name:
            raise Exception("The failure domain that appears in 'weka cluster host' for host ID %s is %s, we expected %s (last failure: %s)"
                % (host_id, failure_domain_from_hosts_list, new_failure_domain_name, last_failure))

        log("Validate the failure domain in the stable resources failure domain is %s, which means the container loaded properly with the right resources" % new_failure_domain_name)
        stable_failure_domain = json.loads(host.ssh_call_with_output("weka", "local", "resources", "--stable", "-J"))['failure_domain']
        if stable_failure_domain != new_failure_domain_name:
            raise Exception("The failure domain applied is %s, we expected %s" % (stable_failure_domain, new_failure_domain_name))

        if is_s3 and not skip_s3_drain:
            s3_start_and_undrain(host)

        changed_hosts += 1
        if not skip_health_checks:
            # We first want to see the cluster as unhealthy before we wait for it to become healthy, so we don't hit a
            #  race where rebuild hasn't started and we already start upgrading the next server
            wait_for_unhealthy_cluster(timeout_secs=wait_unhealthy_timeout_secs)
            wait_for_healthy_cluster()

        wait_end = datetime.now()
        wait_delta = wait_end - wait_start
        log(" === Finished change of %s, %s container to failure domain %s (took %s seconds) ===" % (
            host.hostname, container_name, new_failure_domain_name, wait_delta.total_seconds(), ))

    return changed_hosts, skipped_hosts


def main():
    parser = argparse.ArgumentParser(description='Rolling-upgrade multiple hosts via ssh')
    parser.add_argument('-i', dest='ssh_identity', type=str, help='SSH identity to pass to ssh -i')
    parser.add_argument('--container', dest='container_name', type=str, help='In order to rolling upgrade just one container')
    parser.add_argument('-s', '--skip-health-checks', dest='skip_health_checks', action='store_true', default=False,
                        help='WARNING: DON\'T USE THIS OPTION UNLESS YOU REALLY NEED TO. '
                             'If cluster is unhealthy, don\'t wait for rebuilds, and health checks')
    parser.add_argument('--wait-unhealthy-timeout-secs', dest='wait_unhealthy_timeout_secs', type=int, default=120,
                        help='Time to wait for cluster to become unhealthy before waiting for it to become healthy')

    # S3
    parser.add_argument('--skip-s3-drain', dest='skip_s3_drain', action='store_true', default=False,
                    help='WARNING: DON\'T USE THIS OPTION UNLESS YOU REALLY NEED TO. '
                     'Do not drain and undrain S3 container at all, even if it exists.')
    parser.add_argument('--s3-drain-grace-seconds', dest='s3_drain_grace', type=float, default=80,
                        help='how long to wait to let the load balancer detect that the S3 container is draining')
    parser.add_argument('--s3-drain-timeout-seconds', dest='s3_drain_timeout', type=float, default=60,
                        help='how long to allow for an S3 container to drain before timing out')
    parser.add_argument('--s3-drain-interval-secs', dest='s3_drain_interval', type=float, default=1,
                        help='how often to poll for the drain status while waiting for an S3 host to drain')
    parser.add_argument('--s3-drain-required-checks', dest='s3_drain_required_checks', type=int, default=10,
                        help='how many drain checks in a row are required for a host to be considered drained')
    parser.add_argument('--s3-force-stop-with-failed-drain-check', dest='force_stop_s3_with_failed_drain_check', action='store_true', default=False,
                        help='WARNING: DON\'T USE THIS OPTION UNLESS YOU REALLY NEED TO. '
                        'Force stop the S3 container even if we failed consecutive post-drain IO checks')

    args = parser.parse_args()
    upgrade(
        s3_drain_timeout=args.s3_drain_timeout,
        s3_drain_grace=args.s3_drain_grace,
        s3_drain_interval=args.s3_drain_interval,
        s3_drain_required_checks=args.s3_drain_required_checks,
        force_stop_s3_with_failed_drain_check=args.force_stop_s3_with_failed_drain_check,
        ssh_identity=args.ssh_identity,
        container_name=args.container_name,
        skip_health_checks=args.skip_health_checks,
        wait_unhealthy_timeout_secs=args.wait_unhealthy_timeout_secs,
        skip_s3_drain=args.skip_s3_drain)

def upgrade(s3_drain_timeout, s3_drain_grace, s3_drain_interval, s3_drain_required_checks, force_stop_s3_with_failed_drain_check=False, ssh_identity=None, container_name=None, skip_health_checks=False, wait_unhealthy_timeout_secs=None, skip_s3_drain=False):
    wait_start = datetime.now()
    changed_hosts, skipped_hosts = change_failure_domains(
        s3_drain_timeout, s3_drain_grace, s3_drain_interval, s3_drain_required_checks, force_stop_s3_with_failed_drain_check, ssh_identity, container_name, skip_health_checks, wait_unhealthy_timeout_secs, skip_s3_drain)

    wait_end = datetime.now()
    wait_delta = wait_end - wait_start
    log(" === Finished conversion of failure domains (%s changed, %s skipped, took %s seconds) ===" % (
        changed_hosts, skipped_hosts, wait_delta.total_seconds(), ))

if __name__ == '__main__':
    main()
