#!/usr/bin/env python3

# docs are here: https://www.notion.so/SBC-to-MBC-convertor-3de4a1be68124a08a6d694da7fcaeeea
import json
import logging
import os
import shlex
import subprocess
from enum import Enum
import argparse
from time import sleep, time
import re
from urllib import request, error
from socket import timeout
from concurrent.futures import ThreadPoolExecutor
from resources_generator import GiB

logger = logging.getLogger('mbc divider')


def setup_logger():
    if logger.hasHandlers():
        logger.handlers.clear()
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(name)s - %(levelname)s: %(message)s', '%Y-%m-%d %H:%M:%S')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False


def run_shell_command(command, no_fail=False):
    logger.info('running: {}'.format(command))
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
    output, stderr = process.communicate()
    if process.returncode != 0:
        logger.warning("Something went wrong running: {}".format(command))
        logger.warning("Return Code: {}".format(process.returncode))
        logger.warning("Output: {}".format(output))
        logger.warning("Stderr: {}".format(stderr))
        if not no_fail:
            raise Exception("Error running command (exit code {}): {}".format(process.returncode, command))

    return output


def is_aws():
    with ThreadPoolExecutor() as executor:
        retries = 4
        init_timeout = 0.1
        for i in range(retries):
            try:
                request.urlopen("http://169.254.169.254/2016-09-02/meta-data/", timeout=(1 + i) * init_timeout).read()
                return True
            except error.URLError:
                pass
            except timeout:
                pass
            return False


class ContainerType(Enum):
    DRIVE = 'drives'
    COMPUTE = 'compute'
    FRONTEND = 'frontend'

    def container_name(self):
        return '{}0'.format(self.value)

    def json_name(self):
        return '{}.json'.format(self.container_name())


class Protocols(Enum):
    NFS = 'nfs'
    S3 = 's3'
    SMB = 'smb'


class NetDev:
    def __init__(self, name, identifier, gateway, netmask, ips, mac_address):
        self.name = name
        self.identifier = identifier
        self.gateway = gateway
        self.netmask = netmask
        self.ips = ips
        self.mac_address = mac_address

    def to_cmd(self):
        def _is_pci_address(pci):
            if re.match(r'[0-9a-fA-F]{0,4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]', pci):
                return True
            return False

        def _pci_to_mac(pci):
            path = "/sys/bus/pci/devices/%s/net/" % pci
            dev_info = os.listdir(path)
            dev_name = dev_info.pop()
            addr_file = os.path.join(path, dev_name, 'address')
            with open(addr_file) as f:
                return next(f).strip()

        net_suffix = ''
        if self.ips:
            net_suffix = '/' + '+'.join(self.ips) + '/' + str(self.netmask) + '/' + self.gateway

        if _is_pci_address(self.name) and self.mac_address:
            return self.mac_address + net_suffix
        elif self.name:
            return self.name + net_suffix
        else:
            return self.identifier + net_suffix


def drain_in_progress(sudo):
    s3_cluster_info = json.loads(run_shell_command('/bin/sh -c "weka s3 cluster -J"'))
    protocol = "https" if s3_cluster_info["tls_enabled"] else "http"
    port = s3_cluster_info["port"]
    drain_url = protocol + "://127.0.0.1:" + port + "/minio/drain/mode"
    minio_drain_check_cmd = '/bin/sh -c "{} weka local exec -C s3 curl -sk {}"'.format(sudo, drain_url)
    drain_status = json.loads(run_shell_command(minio_drain_check_cmd))
    return json.loads(drain_status["mode"])


def check_etcd_health(sudo):
    logger.info("Checking etcd Health")
    etcd_health_cmd = '/bin/sh -c "{} weka local exec -C s3 etcdctl endpoint health --cluster -w json"'.format(sudo)
    etcd_status = json.loads(run_shell_command(etcd_health_cmd, True))
    while True:
        if etcd_status:
            if not all(etcd_host["health"] for etcd_host in etcd_status):
                failed_etcd_hosts = [etcd_host["endpoint"] for etcd_host in etcd_status if not etcd_host["health"]]
                logger.error("We have {} failed etcd hosts, from the following ips {}"
                             .format(len(failed_etcd_hosts), failed_etcd_hosts))
                sleep(15)
                etcd_status = json.loads(run_shell_command(etcd_health_cmd, True))
            else:
                return True


def extract_digits(s):
    return "".join(filter(str.isdigit, s))


# This function scans, moves and verifies that the disks are transferred from old host to current (target) host
def safe_drive_scan(drives_container_host_id, old_host_id):
    retries = 15
    drives_list = json.loads(run_shell_command('/bin/sh -c "weka cluster drive --host {} -J"'.format(old_host_id)))
    drives_uuids = [disk["uuid"] for disk in drives_list]
    logger.info("The following drives will be moved to the new container: {}".format(drives_uuids))
    scan_disk_command = '/bin/sh -c "weka cluster drive scan {}"'.format(drives_container_host_id)
    run_shell_command(scan_disk_command)
    sleep(2)
    for i in range(retries):
        drives_list = json.loads(run_shell_command('/bin/sh -c "weka cluster drive --host {} -J"'.format(old_host_id)))
        drives_uuids = [disk["uuid"] for disk in drives_list]
        if not drives_uuids:
            return
    logger.warning("The following drives did not move to the new container, {} retrying".format(drives_uuids))
    raise Exception("The following drives did not move to the new container, {} retrying".format(drives_uuids))


def check_and_fix_machine_identifier_in_failure_domain(host_id):
    host_row = json.loads(run_shell_command('/bin/sh -c "weka cluster host {} -J"'.format(host_id)))[0]
    failure_domain_machine_id = json.loads(run_shell_command(
        '/bin/sh -c "weka debug config show failureDomains[{}].machineIdentifier"'
        .format(extract_digits(host_row['failure_domain_id']))))
    host_row_machine_id = json.loads(run_shell_command(
        '/bin/sh -c "weka debug config show hosts[{}].machineIdentifier"'.format(host_id)))
    if failure_domain_machine_id != host_row_machine_id:
        logger.info('Fixing the machine identifier in {} to fit host {}'.format(host_row['failure_domain_id'], host_id))
        kv_strings_list = []
        for i in range(len(host_row_machine_id)):
            kv_strings_list.append("machineIdentifier[{}]={}".format(i, host_row_machine_id[i]))
        config_assign_cmd = '/bin/sh -c "weka debug config assign failureDomains[{}] {}"'\
            .format(extract_digits(host_row["failure_domain_id"]), " ".join(kv_strings_list))
        try:
            run_shell_command(config_assign_cmd)
        except Exception as e:
            logger.warning("Failed to change the machine identifier for {} with the the following error: {}".format(host_row["failure_domain_id"], e))
            raise e


def wait_for_s3_container(sudo):
    logger.info("Waiting for s3 container to be Ready")
    local_ps_cmd = '/bin/sh -c "{}weka local ps -J"'.format(sudo)
    retries = 10
    for i in range(retries):
        sleep(5)  # wait for s3 container to start
        ps = json.loads(run_shell_command(local_ps_cmd))
        s3_ready = [container for container in ps if
                    container["internalStatus"]["display_status"] == 'READY' and container['type'].lower() == 's3']
        if s3_ready:
            break


def wait_for_nodes_to_be_down(container_id,):
    retries = 90
    nodes_command = '/bin/sh -c "weka cluster nodes --host {} -J"'.format(container_id)
    nodes_output = {}
    nodes_output = json.loads(run_shell_command(nodes_command))
    nodes_list = []
    for node in nodes_output:
        nodes_list.append(node['node_id'])
    logger.debug('Waiting for nodes {} to reach DOWN state'.format(
        nodes_list))  # TODO: strip from NodeId?

    notDownNodes = []
    for i in range(retries):
        nodes_output = json.loads(run_shell_command(nodes_command))
        notDownNodes = []
        for node in nodes_output:
            if node['status'] != 'DOWN':
                logger.debug('{} is {}'.format(node['node_id'], node['status']))
                notDownNodes.append(node['node_id'])

        if not notDownNodes:
            logger.debug('all nodes are DOWN')
            return

        sleep(1)

    raise Exception("nodes were not down after 90 seconds! (not down nodes:{})".format(notDownNodes))


def wait_for_container_to_be_ready(container_type, sudo):
    retries = 30
    sleep(15)
    status_command = '/bin/sh -c "{}weka local status -J"'.format(sudo)
    local_status = {}
    local_status = json.loads(run_shell_command(status_command))
    logger.info('Waiting for {} containers to reach READY state, currently:{}'.format(
        container_type,
        local_status[container_type.container_name()]['status']['internalStatus']['state']))

    for i in range(retries):
        sleep(1)

        local_status = json.loads(run_shell_command(status_command))
        if local_status[container_type.container_name()]['status']['internalStatus']['state'] == 'READY':
            break

def wait_for_host_deactivate(host_id):
    get_host_from_hosts_list_cmd = '/bin/sh -c "weka cluster host {} -J"'.format(host_id)
    logger.info('Waiting for host to deactivate')
    retries = 60
    for i in range(retries):
        host_row = json.loads(run_shell_command(get_host_from_hosts_list_cmd))
        if host_row[0]['status'] == 'INACTIVE':
            return
        sleep(1)

    logger.error('host {} did not reach inactive status'.format(host_id))

def wait_for_buckets_redistribution():
    get_buckets_status_cmd = '/bin/sh -c "weka status -J"'
    retries = 60
    logger.info('Waiting for buckets redistribution')
    for i in range(retries):
        weka_status = json.loads(run_shell_command(get_buckets_status_cmd))
        buckets = weka_status["buckets"]
        if buckets["active"] == buckets["total"]:
            return
        sleep(2)

    logger.info('Some buckets have not redistributed yet')
    exit(1)


def s3_has_active_ios(host_id):
    validate_drain_s3_cmd = '/bin/sh -c "weka debug jrpc container_get_drain_status hostId={}"'.format(host_id)
    s3_drain_status = json.loads(run_shell_command(validate_drain_s3_cmd))
    return not s3_drain_status


def wait_for_s3_drain(timeout, host_id, interval, required_checks, hostname, force, sudo):
    successful_checks_in_a_row = 0
    start = time()
    while time() - start < timeout:
        try:
            minio_in_drain_mode = drain_in_progress(sudo)
            has_active_ios = s3_has_active_ios(host_id)
            if minio_in_drain_mode and not has_active_ios:
                successful_checks_in_a_row += 1
                logger.info("Got %s successful drain checks in a row on host %s; We need %s"
                    % (successful_checks_in_a_row, hostname, required_checks))
                if successful_checks_in_a_row >= required_checks:
                    return
            else:
                logger.warning("Drain on host %s hasn't finished yet. Is Minio in drain mode? %s. Are there active IOs? %s."
                    % (hostname, minio_in_drain_mode, has_active_ios))
                successful_checks_in_a_row = 0
            sleep(interval)
        except Exception as e:
            logger.error("Error while waiting for draining S3 container of %s to finish: '%s'; retrying" % (hostname, e))
            successful_checks_in_a_row = 0

    if force:
        logger.error("Timed out while waiting for S3 container IOs to complete on %s, but force flag allows to stop S3 container" % (hostname, ))
        return

    raise Exception("Timed out waiting for draining S3 container of %s to finish" % hostname)


dry_run = False


def main():
    setup_logger()

    parser = argparse.ArgumentParser()
    parser.add_argument("--resources-path", dest='resources_path', nargs="?", default='',
                        help="Load resource from file")
    # help='Run the script without execution of weka commands'
    parser.add_argument('--dry-run', dest='dry_run', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--force', '-f', dest='force', action='store_true',
                        help='Override backup resources')
    parser.add_argument('--s3-drain-gracetime', '--d', nargs="?", default=80, type=int, dest="s3_drain_gracetime",
                        help='Set a gracetime for s3 drain')
    parser.add_argument('--drive-dedicated-cores', '--D', nargs="?", default=0, type=int, dest="drive_dedicated_cores",
                        help='Set drive-dedicated-cores')
    parser.add_argument('--compute-dedicated-cores', '--C', nargs="?", default=0, type=int,
                        dest="compute_dedicated_cores", help='Set compute_dedicated_cores')
    parser.add_argument('--frontend-dedicated-cores', '--F', nargs="?", default=0, type=int,
                        dest="frontend_dedicated_cores", help='Set frontend_dedicated_cores')
    parser.add_argument('--limit-maximum-memory', '--m', nargs="?", default=0, type=float,
                        dest="limit_maximum_memory", help='override maximum memory in GiB')
    parser.add_argument('--keep-s3-up', '-S', dest='keep_s3_up', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--s3-force-stop-with-failed-drain-check', '-c', dest='dont_enforce_drain', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument("--allocate-nics-exclusively", action='store_true', dest='allocate_nics_exclusively',
                        help="Set one unique net device per each io node, relevant when using virtual functions (VMware, KVM etc.)")
    parser.add_argument("--use-only-nic-identifier", action='store_true', dest='use_only_nic_identifier',
                        help="use only the nic identifier when allocating the nics")
    parser.add_argument("--remove-old-container", action='store_true', dest='remove_old_container',
                        help=argparse.SUPPRESS)

    args = parser.parse_args()
    global dry_run
    dry_run = args.dry_run
    if dry_run and not args.resources_path:
        logger.error("dry run needs resources path to continue, exiting")
        quit(1)

    is_root = os.geteuid() == 0
    sudo = ''
    if not is_root:
        sudo = 'sudo '

    local_ps_cmd = '/bin/sh -c "{}weka local ps -J"'.format(sudo)
    ps = json.loads(run_shell_command(local_ps_cmd))
    container_name = 'default'
    if ps:
        multiple_containers = 0
        for container in ps:
            if container["internalStatus"]["display_status"] == 'READY' and container['type'].lower() == 'weka':
                multiple_containers += 1
                container_name = container['name']
        if multiple_containers > 1:
            logger.warning("This server already has multiple backend containers, skipping")
            exit(0)
        if not multiple_containers:
            logger.error("This server's containers are not ready: Cannot convert unhealthy hosts")
            exit(1)
    else:
        logger.warning("Weka is not installed on this server, skipping")
        exit(0)
    #  TODO: maybe: check mounts for every container
    local_status_cmd = '/bin/sh -c "{}weka local status -J"'.format(sudo)
    status = json.loads(run_shell_command(local_status_cmd))
    if status[container_name]['mount_points']:
        logger.warning("This server has an active WekaFS mount, please unmount before continuing")
        exit(1)
    # TODO: for new script generate backup with datetime
    backup_file_name = os.path.abspath('resources.json.backup')
    if os.path.exists(backup_file_name) and not args.force:
        logger.warning("Backup resources file {} already exists, will not override it".format(backup_file_name))
        exit(1)

    backup_resources_command = '/bin/sh -c "{}weka local resources export {}"'.format(sudo, backup_file_name)
    logger.info("Backing up resources to {}".format(os.path.abspath(backup_file_name)))
    run_shell_command(backup_resources_command)
    resource_path = args.resources_path
    # Read content of the backup file - these are the current resources
    with open(resource_path if len(resource_path) else backup_file_name, 'r') as f:
        prev_resources = json.loads(f.read())

    get_host_id_command = '/bin/sh -c "weka debug manhole getServerInfo --slot=0"'
    server_info = json.loads(run_shell_command(get_host_id_command))
    current_host_id = int(server_info['hostIdValue'])

    pinned_compute_cores = []
    pinned_frontend_cores = []
    pinned_drive_cores = []
    compute_cores = args.compute_dedicated_cores
    frontend_cores = args.frontend_dedicated_cores
    drive_cores = args.drive_dedicated_cores
    old_failure_domain = prev_resources['failure_domain']
    # TODO: new script convert to manual FD
    # TODO: add enforcement for manual FD
    memory = prev_resources['memory']
    if args.limit_maximum_memory:
        memory = int(args.limit_maximum_memory * GiB)
    failure_domain = ""
    failure_domain_for_local = ""
    if old_failure_domain:
        failure_domain = '--failure-domain ' + old_failure_domain
        failure_domain_for_local = '--name ' + old_failure_domain
    else:
        check_and_fix_machine_identifier_in_failure_domain(current_host_id)

    for slot in prev_resources['nodes']:
        roles = prev_resources['nodes'][slot]['roles']
        coreId = prev_resources['nodes'][slot]['core_id']
        if len(roles) > 1:
            logger.warning(
                "This script does not support multiple node roles. Please contact costumer support for more information")
            exit(1)
        if roles[0] == "COMPUTE" and not args.compute_dedicated_cores:
            compute_cores += 1
            if coreId != 4294967295:
                pinned_compute_cores.append(coreId)
        elif roles[0] == "DRIVES" and not args.drive_dedicated_cores:
            drive_cores += 1
            if coreId != 4294967295:
                pinned_drive_cores.append(coreId)
        elif roles[0] == "FRONTEND" and not args.frontend_dedicated_cores:
            frontend_cores += 1
            if coreId != 4294967295:
                pinned_frontend_cores.append(coreId)
    if len(prev_resources['backend_endpoints']) < 1:
        logger.warning('The host\'s resources are missing the backend endpoints, is this host part of a Weka cluster?')
        exit(1)

    network_devices = []

    get_net_cmd = '/bin/sh -c "weka cluster host net {} -J"'.format(current_host_id)
    net_devs = json.loads(run_shell_command(get_net_cmd))
    for netDev in net_devs:
        network_devices.append(NetDev(netDev['name'], netDev['identifier'], netDev['gateway'], netDev['netmask_bits'],
                                      list(set(netDev['ips'])), netDev['net_devices'][0]['mac_address']))
        logger.debug("Adding net devices: {}".format(network_devices[-1].to_cmd()))
    # TODO: not lose network label

    retries = 180  # sleeps should be 1 second each, so this is a "timeout" of 180s
    # S3 check
    host_id_str = 'HostId<{}>'.format(current_host_id)
    logger.info('Checking for active protocols on the host')
    protocols_in_host = []
    s3_status_command = '/bin/sh -c "weka s3 cluster status -J"'
    s3_status = json.loads(run_shell_command(s3_status_command))
    if host_id_str in s3_status:
        if len(s3_status) < 4:
            logger.warning('We have only {} hosts in s3 cluster, in order to convert cluster we need at list 4'.format(
                len(s3_status)))
            exit(1)
        check_etcd_health(sudo)

    # SMB check
    smb_status_command = '/bin/sh -c "weka smb cluster status -J"'
    smb_status = json.loads(run_shell_command(smb_status_command))
    if host_id_str in smb_status:
        if len(smb_status) < 4:
            logger.warning('We have only {} hosts in SMB cluster, in order to convert cluster we need at list 4'.format(
                len(smb_status)))
            exit(1)
        for i in range(retries):
            smb_status = json.loads(run_shell_command(smb_status_command))
            if all(status for status in smb_status.values()):
                break
            sleep(1)
        smb_status = json.loads(run_shell_command(smb_status_command))
        if not all(status for status in smb_status.values()):
            logger.warning("SMB cluster never became ready, cannot convert")
            exit(1)

    # NFS check
    nfs_interface_groups = '/bin/sh -c "weka nfs interface-group -J"'
    nfs_igs = json.loads(run_shell_command(nfs_interface_groups))
    if nfs_igs:
        logger.info('There is NFS configured in this cluster')
        for ig in nfs_igs:
            for port in ig['ports']:
                port_host_id = extract_digits(port['host_id'])
                if int(port_host_id) == current_host_id and len(ig['ports']) < 2:
                    logger.error(
                        'We have only {} hosts in NFS interface group, in order to convert cluster we need at list 2'
                        .format(len(ig['ports'])))
                    exit(1)

    # S3 drain and removal
    if host_id_str in s3_status:
        if not all(status for status in s3_status.values()):
            logger.info('Waiting for S3 cluster to be fully healthy before converting server')
            if drain_in_progress(sudo):
                logger.info('S3 is currently draining, undraining in order to get to ready status')
                undrain_s3_cmd = '/bin/sh -c "weka s3 cluster undrain {}"'.format(current_host_id)
                run_shell_command(undrain_s3_cmd)
            while True:
                sleep(1)
                s3_status = json.loads(run_shell_command(s3_status_command))
                if all(status for status in s3_status.values()):
                    break

        drain_s3_cmd = '/bin/sh -c "weka s3 cluster drain {}"'.format(current_host_id)
        logger.warning('Draining S3 container')
        run_shell_command(drain_s3_cmd)
        s3_drain_grace_period = int(args.s3_drain_gracetime)
        sleep(s3_drain_grace_period)
        # validate drain
        hostname = os.uname()[1]
        s3_drain_timeout = 60
        wait_for_s3_drain(s3_drain_timeout, current_host_id, 1, 10, hostname, args.dont_enforce_drain, sudo=sudo)
        protocols_in_host.append(Protocols.S3)
        if not args.keep_s3_up:
            logger.warning('Removing container from S3 cluster')
            s3_update_command = '/bin/sh -c "weka s3 cluster update --host {}"'
            s3_hosts_list = []
            for k in s3_status.keys():
                s3_host_id = extract_digits(k)
                if int(s3_host_id) == current_host_id:
                    continue
                s3_hosts_list.append(s3_host_id)
            hosts_list = ','.join(s3_hosts_list)
            run_shell_command(s3_update_command.format(hosts_list))
            for i in range(retries):
                s3_status = json.loads(run_shell_command(s3_status_command))
                if host_id_str not in s3_status:
                    break
                sleep(1)
            s3_status = json.loads(run_shell_command(s3_status_command))
            if host_id_str in s3_status:
                logger.warning("Failed removing host {} from s3 cluster".format(current_host_id))
                exit(1)

    # SMB removal
    if host_id_str in smb_status:
        logger.info('Removing host from SMB cluster')
        protocols_in_host.append(Protocols.SMB)
        remove_smb_host_cmd = '/bin/sh -c "weka smb cluster hosts remove --samba-hosts {} -f"'.format(current_host_id)
        run_shell_command(remove_smb_host_cmd)
        for i in range(retries):
            smb_status = json.loads(run_shell_command(smb_status_command))
            if host_id_str not in smb_status:
                break
            sleep(1)
        smb_status = json.loads(run_shell_command(smb_status_command))
        if host_id_str in smb_status:
            logger.warning("Failed removing host {} from SMB cluster".format(current_host_id))
            exit(1)

    # NFS removal
    nfs_interface_groups = '/bin/sh -c "weka nfs interface-group -J"'
    nfs_igs = json.loads(run_shell_command(nfs_interface_groups))
    nfs_ifgs_to_add = []
    if nfs_igs:
        logger.warning('There is nfs setup in this cluster')
        for ig in nfs_igs:
            for port in ig['ports']:
                port_host_id = extract_digits(port['host_id'])
                if int(port_host_id) == current_host_id:
                    logger.info('Removing host from nfs interface group {}'.format(ig['name']))
                    nfs_remove_port_cmd = '/bin/sh -c "weka nfs interface-group port delete {} {} {} -f"' \
                        .format(ig['name'], current_host_id, port['port'])
                    nfs_ifgs_to_add.append((ig['name'], port['port'], ig['allow_manage_gids']))
                    run_shell_command(nfs_remove_port_cmd)
        if nfs_ifgs_to_add:
            protocols_in_host.append(Protocols.NFS)
            host_is_an_active_port = False
            for i in range(retries):
                nfs_igs = json.loads(run_shell_command(nfs_interface_groups))
                host_is_an_active_port = False
                for ig in nfs_igs:
                    for port in ig['ports']:
                        port_host_id = extract_digits(port['host_id'])
                        if int(port_host_id) == current_host_id:
                            host_is_an_active_port = True
                            break
                if not host_is_an_active_port:
                    break
                sleep(1)
            if host_is_an_active_port:
                logger.warning('Failed removing nfs port')
                exit(1)

    logger.info('Validating no protocols containers are running')
    sleep(5)  # TODO: Why do we sleep?
    local_ps_cmd = '/bin/sh -c "{}weka local ps -J"'.format(sudo)
    for i in range(10):
        containers = json.loads(run_shell_command(local_ps_cmd))
        has_protocols_containers = False
        for c in containers:
            if c['type'] != 'weka':
                has_protocols_containers = True
        if not has_protocols_containers:
            break
        sleep(1)

    get_host_list = '/bin/sh -c "weka cluster host -b -J"'
    weka_hosts_list = json.loads(run_shell_command(get_host_list))
    join_ips_list = []
    for host in weka_hosts_list:
        # If this is the host we're currently open, skip adding it to join-ips
        if host['host_id'] == host_id_str:
            continue

        join_ips_list.append(str(host['ips'][0]))  # + ':' + str(host['mgmt_port']))
        if len(join_ips_list) > 10:
            break

    join_ips = '--join-ips=' + ','.join(join_ips_list)
    logger.info('IPs for Joining the cluster: {}'.format(join_ips))
    mgmt_ips_list = []
    if prev_resources['ips']:
        mgmt_ips_list = prev_resources['ips']
    else:
        # Find ourselves in the list, and use ips from hosts_list
        for host in weka_hosts_list:
            if host['host_id'] != host_id_str:
                continue
            mgmt_ips_list = host['ips']
    management_ips = '--management-ips=' + ','.join(mgmt_ips_list)
    logger.info('Management IPs selected: {}'.format(management_ips))
    logger.info('Stopping old container')
    stop_container_cmd = '/bin/sh -c "{}weka local stop"'.format(sudo)
    run_shell_command(stop_container_cmd)

    all_net = ' '
    for netDev in network_devices:
        all_net += netDev.to_cmd() + ' '

    compute_cores_cmd = ' --compute-dedicated-cores {}'.format(compute_cores) if (compute_cores > 0) else ''
    if len(pinned_compute_cores):
        compute_cores_cmd += ' --compute-core-ids '
        for core_id in pinned_compute_cores:
            compute_cores_cmd += str(core_id) + ' '
    drive_cores_cmd = ' --drive-dedicated-cores {}'.format(drive_cores) if (drive_cores > 0) else ''
    if len(pinned_drive_cores):
        drive_cores_cmd += ' --drive-core-ids '
        for core_id in pinned_drive_cores:
            drive_cores_cmd += str(core_id) + ' '
    frontend_cores_cmd = ' --frontend-dedicated-cores {}'.format(frontend_cores)
    if len(pinned_frontend_cores):
        frontend_cores_cmd += ' --frontend-core-ids '
        for core_id in pinned_frontend_cores:
            frontend_cores_cmd += str(core_id) + ' '
    allocate_nics_exclusively = ' --allocate-nics-exclusively' if args.allocate_nics_exclusively is True else ''
    use_auto_fd = ' --use-auto-failure-domain' if not old_failure_domain else ''
    memory_cmd = ' --weka-hugepages-memory ' + str(memory) + 'B' if memory else ''
    use_only_identifier = ' --use-only-nic-identifier' if args.use_only_nic_identifier else ''
    resource_generator_command = '/bin/sh -c "/tmp/resources_generator.py --net {}{}{}{}{}{}{}{} -f"'.format(
        all_net,
        compute_cores_cmd,
        drive_cores_cmd,
        frontend_cores_cmd,
        memory_cmd,
        use_auto_fd,
        allocate_nics_exclusively,
        use_only_identifier
    )
    logger.info('Running resources-generator with cmd: {}'.format(resource_generator_command))
    run_shell_command(resource_generator_command)
    logger.info('Releasing old hugepages allocation')
    path_to_huge = '/opt/weka/data/agent/containers/state/{}/huge'.format(container_name)
    path_to_huge1g = '/opt/weka/data/agent/containers/state/{}/huge1G'.format(container_name)
    if os.path.exists(path_to_huge) or os.path.exists(path_to_huge1g):
        find_and_remove_cmd = '/bin/sh -c "{}find {}* -name weka_\* -delete"'.format(sudo, path_to_huge)
        run_shell_command(find_and_remove_cmd)
    logger.info('Starting new containers')

    for container_type in ContainerType:
        if container_type == ContainerType.FRONTEND:
            if frontend_cores == 0:
                continue
            elif args.keep_s3_up:
                logger.info("Applying resources of type {} on container {}".format(container_type, container_name))
                import_resources_command = '/bin/sh -c "{}weka local resources import {} -C {} -f"'.format(
                    sudo,
                    container_type.json_name(),
                    container_name,
                )
                run_shell_command(import_resources_command)
                set_mgmt_ip_command = '/bin/sh -c "{}weka local resources management-ips {} -C {}"'.format(
                    sudo,
                    " ".join(mgmt_ips_list),
                    container_name,
                )
                run_shell_command(set_mgmt_ip_command)
                set_join_ips_command = '/bin/sh -c "{}weka local resources join-ips {} -C {}"'.format(
                    sudo,
                    " ".join(join_ips_list),
                    container_name,
                )
                run_shell_command(set_join_ips_command)
                if old_failure_domain:
                    set_FD_command = '/bin/sh -c "{}weka local resources failure-domain {} -C {}"'.format(
                        sudo,
                        failure_domain_for_local,
                        container_name,
                    )
                    run_shell_command(set_FD_command)
                apply_command = '/bin/sh -c "{}weka local resources apply -C {} -f"'.format(
                    sudo,
                    container_name,
                )
                run_shell_command(apply_command)
                start_command = '/bin/sh -c "{}weka local start {}"'.format(
                    sudo,
                    container_name,
                )
                run_shell_command(start_command)
                if Protocols.S3 in protocols_in_host:
                    start_command = '/bin/sh -c "{}weka local start {}"'.format(
                        sudo,
                        "s3",
                    )
                    run_shell_command(start_command)
                    logger.info("Starting container {}".format(container_name))
                    logger.info("undrain s3 container {}".format(container_name))
                    wait_for_s3_container(sudo)
                    undrain_s3_cmd = '/bin/sh -c "weka s3 cluster undrain {}"'.format(current_host_id)
                    run_shell_command(undrain_s3_cmd)
                continue

        setup_host_command = '/bin/sh -c "{}weka local setup host --timeout 10m --name={} --resources-path={} {} {} {} --disable"'.format(
            sudo,
            container_type.container_name(),
            container_type.json_name(),
            failure_domain,
            management_ips,
            join_ips
        )
        logger.info("Starting container of type {} using the following command: {}".format(
            container_type.name, setup_host_command))
        run_shell_command(setup_host_command)
        status_command = '/bin/sh -c "{}weka local status -J"'.format(sudo)
        if container_type == ContainerType.DRIVE:
            wait_for_container_to_be_ready(ContainerType.DRIVE, sudo)
            for i in range(retries):
                sleep(1)
                try:
                    local_status = json.loads(run_shell_command(status_command))
                    if local_status[ContainerType.DRIVE.container_name()]['status']['internalStatus']['state'] != 'READY':
                        continue
                    server_info = json.loads(run_shell_command(get_host_id_command))
                    new_drive_host_id = server_info['hostIdValue']
                    wait_for_nodes_to_be_down(current_host_id)
                    #safe_drive_scan assumes that all old nodes are down
                    safe_drive_scan(new_drive_host_id, current_host_id)
                    logger.info('Done scanning drives')
                    break

                except Exception as e:
                    logger.error("Error querying container status and invoking scan: {}".format(str(e)))


    if protocols_in_host:
        wait_for_container_to_be_ready(ContainerType.FRONTEND, sudo)
        fe_container_name = ContainerType.FRONTEND.container_name()
        if args.keep_s3_up:
            fe_container_name = container_name
        get_resources_cmd = '/bin/sh -c "{}weka local resources -C {} -J"'.format(
            sudo,
            fe_container_name)
        frontend_resources = json.loads(run_shell_command(get_resources_cmd))
        get_host_id_command = '/bin/sh -c "weka debug manhole getServerInfo --slot=0 -P {}"' \
            .format(frontend_resources['base_port'])
        server_info = json.loads(run_shell_command(get_host_id_command))
        frontend_hostid = server_info['hostIdValue']
        for protocol in protocols_in_host:
            logger.info("Adding {} protocol to frontend container".format(protocol.name))
            if protocol == Protocols.SMB:
                add_smb_host_cmd = '/bin/sh -c "weka smb cluster hosts add --samba-hosts {} -f"' \
                    .format(frontend_hostid)
                run_shell_command(add_smb_host_cmd)
            elif protocol == Protocols.S3:
                if not args.keep_s3_up:
                    hosts_list = ''
                    for k in s3_status.keys():
                        if int(extract_digits(k)) == current_host_id:
                            continue
                        hosts_list += extract_digits(k) + ','
                    hosts_list += str(frontend_hostid)
                    s3_update_command = '/bin/sh -c "weka s3 cluster update --host {}"'
                    run_shell_command(s3_update_command.format(hosts_list))
                wait_for_s3_container(sudo)
                check_etcd_health(sudo)
            elif protocol == Protocols.NFS:
                if is_aws():
                    set_local_nfs_server_command = '/bin/sh -c "weka debug manhole set_local_nfs_server --slot=0 -P {} val=true"' \
                        .format(frontend_resources['base_port'])
                    run_shell_command(set_local_nfs_server_command)
                for ig in nfs_ifgs_to_add:
                    nfs_add_port_cmd = '/bin/sh -c "weka nfs interface-group port add {} {} {}"' \
                        .format(ig[0], frontend_hostid, ig[1])
                    run_shell_command(nfs_add_port_cmd)
                    if ig[2]:
                        nfs_legacy = True

    wait_for_buckets_redistribution()
    container_enable_command = '/bin/sh -c "{}weka local enable"'.format(sudo)
    run_shell_command(container_enable_command)

    logger.info('Starting cleanup: The old container will be removed locally and removed from the cluster')
    if not args.keep_s3_up:
        container_disable_command = '/bin/sh -c "{}weka local disable {} "'.format(sudo, container_name)
        run_shell_command(container_disable_command)
        host_deactivate_command = '/bin/sh -c "weka cluster host deactivate {}"'.format(current_host_id)
        run_shell_command(host_deactivate_command)
        wait_for_host_deactivate(current_host_id)
        host_remove_command = '/bin/sh -c "weka cluster host remove {} --no-unimprint"'.format(current_host_id)
        run_shell_command(host_remove_command)
        logger.info('the old container {} is disabled and stopped, please remove it after the conversion is done'.format(container_name))
        if args.remove_old_container:
            container_rm_command = '/bin/sh -c "{}weka local rm {} -f"'.format(sudo, container_name)
            run_shell_command(container_rm_command)

    for ct in ContainerType:
        if os.path.exists(ct.json_name()):
            os.remove(ct.json_name())
    if os.path.exists(backup_file_name):
        os.remove(backup_file_name)
    logger.info('Finished cleanup')
    container_delete_command = '/bin/sh -c "{}weka local status -v"'.format(sudo)
    print(run_shell_command(container_delete_command).decode())
    logger.info("\nFinished moving server to MBC architecture")


if '__main__' == __name__:
    main()
