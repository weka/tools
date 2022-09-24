#!/usr/bin/env python3

# docs are here: https://www.notion.so/SBC-to-MBC-convertor-3de4a1be68124a08a6d694da7fcaeeea
import json
import logging
import os
import shlex
import subprocess
from enum import Enum
import argparse
from time import sleep
import re
from urllib import request, error
from concurrent.futures import ThreadPoolExecutor
from resources_generator import GiB
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')
logger = logging.getLogger('mbc divider')


def run_shell_command(command):
    if dry_run:
        logger.debug('dry_run ot running'.format(command))
        return 0

    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
    output, stderr = process.communicate()
    if process.returncode != 0:
        logger.warning("Something went wrong running: {}".format(command))
        logger.warning("Return Code: {}".format(process.returncode))
        logger.warning("Output: {}".format(output))
        logger.warning("Stderr: {}".format(stderr))
        exit(1)
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
            return False


class ContainerType(Enum):
    COMPUTE = 'compute'
    DRIVE = 'drives'
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


def extract_digits(s):
    return "".join(filter(str.isdigit, s))


dry_run = False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resources-path", dest='resources_path', nargs="?", default='',
                        help="Load resource from file")
    # help='Run the script without execution of weka commands'
    parser.add_argument('--dry-run', dest='dry_run', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--force', '-f', dest='force', action='store_true',
                        help='Override backup resources')
    parser.add_argument('--s3-drain-gracetime', '--d', nargs="?", default=11, type=int, dest="s3_drain_gracetime",
                        help='Set a gracetime for s3 drain')
    parser.add_argument('--drive-dedicated-cores', '--D', nargs="?", default=0, type=int, dest="drive_dedicated_cores",
                        help='Set drive-dedicated-cores')
    parser.add_argument('--compute-dedicated-cores', '--C', nargs="?", default=0, type=int,
                        dest="compute_dedicated_cores", help='Set compute_dedicated_cores')
    parser.add_argument('--frontend-dedicated-cores', '--F', nargs="?", default=0, type=int,
                        dest="frontend_dedicated_cores", help='Set frontend_dedicated_cores')
    parser.add_argument('--limit-maximum-memory', '--m', nargs="?", default=0, type=float,
                        dest="limit_maximum_memory", help='override maximum memory in GiB')
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
            if container["internalStatus"]["display_status"] == 'READY' and container['type'] == 'weka':
                multiple_containers += 1
                container_name = container['name']
        if multiple_containers > 1:
            logger.debug("This host is already an MBC, skipping")
            exit(0)
        if not multiple_containers:
            logger.warning("This host has no ready container, cannot convert unhealthy hosts")
            exit(1)
    else:
        logger.debug("This machine has no weka, skipping")
        exit(0)
    local_status_cmd = '/bin/sh -c "{}weka local status -J"'.format(sudo)
    status = json.loads(run_shell_command(local_status_cmd))
    if status[container_name]['mount_points']:
        logger.warning("This BE host has an active mount, please remove this mount before continuing")
        exit(1)

    backup_file_name = os.path.abspath('resources.json.backup')
    if os.path.exists(backup_file_name) and not args.force:
        logger.warning("Backup resources file {} already exists, will not override it".format(backup_file_name))
        exit(1)

    backup_resources_command = '/bin/sh -c "{}weka local resources export {}"'.format(sudo, backup_file_name)
    logger.debug("Backing up resources to {}".format(os.path.abspath(backup_file_name)))
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
    failure_domain = prev_resources['failure_domain']
    memory = prev_resources['memory']
    if args.limit_maximum_memory:
        memory = int(args.limit_maximum_memory * GiB)

    management_ips = '--management-ips ' + ','.join(prev_resources['ips'])
    if failure_domain:
        failure_domain = '--failure-domain ' + failure_domain
    for slot in prev_resources['nodes']:
        roles = prev_resources['nodes'][slot]['roles']
        coreId = prev_resources['nodes'][slot]['core_id']
        if len(roles) > 1:
            logger.warning("This script does not support multiple node roles. Please contact costumer support")
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
        logger.warning('The host resources are missing the the backend endpoints, is this host part of a Weka cluster?')
        exit(1)
    network_devices = []

    get_host_list = '/bin/sh -c "weka cluster host -b -J"'
    weka_hosts_list = json.loads(run_shell_command(get_host_list))
    get_net_cmd = '/bin/sh -c "weka cluster host net {} -J"'.format(current_host_id)
    net_devs = json.loads(run_shell_command(get_net_cmd))
    for netDev in net_devs:
        network_devices.append(NetDev(netDev['name'], netDev['identifier'], netDev['gateway'], netDev['netmask_bits'],
                                      list(set(netDev['ips'])), netDev['net_devices'][0]['mac_address']))
        logger.debug("add net devices: {}".format(network_devices[-1].to_cmd()))
    retries = 5
    host_id_str = 'HostId<{}>'.format(current_host_id)
    logger.debug('Checking for active protocols on the host')
    protocols_in_host = []
    s3_status_command = '/bin/sh -c "weka s3 cluster status -J"'
    s3_status = json.loads(run_shell_command(s3_status_command))
    if host_id_str in s3_status:
        if len(s3_status) < 4:
            logger.warning('We have only {} hosts in s3 cluster, in order to convert cluster we need at list 4'.format(
                len(s3_status)))
            exit(1)
    smb_status_command = '/bin/sh -c "weka smb cluster status -J"'
    smb_status = json.loads(run_shell_command(smb_status_command))
    if host_id_str in smb_status:
        if len(smb_status) < 4:
            logger.warning('We have only {} hosts in smb cluster, in order to convert cluster we need at list 4'.format(
                len(smb_status)))
            exit(1)
        for i in range(retries):
            smb_status = json.loads(run_shell_command(smb_status_command))
            if all(status for status in smb_status.values()):
                break
            sleep(10)
        smb_status = json.loads(run_shell_command(smb_status_command))
        if not all(status for status in smb_status.values()):
            logger.warning("SMB cluster never became ready, cannot convert")
            exit(1)
    nfs_interface_groups = '/bin/sh -c "weka nfs interface-group -J"'
    nfs_igs = json.loads(run_shell_command(nfs_interface_groups))
    if nfs_igs:
        logger.debug('There is nfs setup in this cluster')
        for ig in nfs_igs:
            for port in ig['ports']:
                port_host_id = extract_digits(port['host_id'])
                if int(port_host_id) == current_host_id and len(ig['ports']) < 2:
                    logger.warning(
                        'We have only {} hosts in nfs interface group, in order to convert cluster we need at list 2'
                        .format(len(ig['ports'])))
                    exit(1)
    if host_id_str in s3_status:
        if not all(status for status in s3_status.values()):
            logger.debug('waiting for s3 cluster to be fully healthy before converting host')
            for i in range(retries):
                sleep(10)
                s3_status = json.loads(run_shell_command(s3_status_command))
                if all(status for status in s3_status.values()):
                    break
            if not all(status for status in s3_status.values()):
                logger.warning('s3 cluster never become ready. can not convert host')
                exit(1)

        drain_s3_cmd = '/bin/sh -c "weka s3 cluster drain {}"'.format(current_host_id)
        logger.debug('Draining s3 host')
        run_shell_command(drain_s3_cmd)
        s3_drain_grace_period = int(args.s3_drain_gracetime)
        sleep(s3_drain_grace_period)
        protocols_in_host.append(Protocols.S3)
        logger.debug('Removing host from s3 cluster')
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
            sleep(3)
        s3_status = json.loads(run_shell_command(s3_status_command))
        if host_id_str in s3_status:
            logger.warning("Failed removing host {} from s3 cluster".format(current_host_id))
            exit(1)

    if host_id_str in smb_status:
        logger.debug('Removing host from SMB cluster')
        protocols_in_host.append(Protocols.SMB)
        remove_smb_host_cmd = '/bin/sh -c "weka smb cluster hosts remove --samba-hosts {} -f"'.format(current_host_id)
        run_shell_command(remove_smb_host_cmd)
        for i in range(retries):
            smb_status = json.loads(run_shell_command(smb_status_command))
            if host_id_str not in smb_status:
                break
            sleep(3)
        smb_status = json.loads(run_shell_command(smb_status_command))
        if host_id_str in smb_status:
            logger.warning("Failed removing host {} from SMB cluster".format(current_host_id))
            exit(1)

    nfs_interface_groups = '/bin/sh -c "weka nfs interface-group -J"'
    nfs_igs = json.loads(run_shell_command(nfs_interface_groups))
    nfs_ifgs_to_add = []
    if nfs_igs:
        logger.debug('There is nfs setup in this cluster')
        for ig in nfs_igs:
            for port in ig['ports']:
                port_host_id = extract_digits(port['host_id'])
                if int(port_host_id) == current_host_id:
                    logger.debug('Removing host from nfs interface group {}'.format(ig['name']))
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
                sleep(3)
            if host_is_an_active_port:
                logger.warning('Failed removing nfs port')
                exit(1)

    logger.debug('Validating no protocols containers are running')
    sleep(5)
    local_ps_cmd = '/bin/sh -c "{}weka local ps -J"'.format(sudo)
    for i in range(5):
        containers = json.loads(run_shell_command(local_ps_cmd))
        has_protocols_containers = False
        for c in containers:
            if c['type'] != 'weka':
                has_protocols_containers = True
        if not has_protocols_containers:
            break
        sleep(2)

    join_ips = '--join-ips='
    join_ips_list = []
    for host in weka_hosts_list:
        if host['ips'][0] == prev_resources['ips'][0]:
            continue
        join_ips_list.append(str(host['ips'][0]) + ':' + str(host['mgmt_port']))
        if len(join_ips_list) > 10:
            break

    join_ips += ','.join(join_ips_list)
    logger.debug('IPs for Joining the cluster: {}'.format(join_ips))

    logger.debug('Stopping old container')
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
    frontend_cores_cmd = ' --frontend-dedicated-cores {}'.format(frontend_cores) if (frontend_cores > 0) else ''
    if len(pinned_frontend_cores):
        frontend_cores_cmd += ' --frontend-core-ids '
        for core_id in pinned_frontend_cores:
            frontend_cores_cmd += str(core_id) + ' '

    memory_cmd = ' --weka-hugepages-memory ' + str(memory) + 'B' if memory else ''
    resource_generator_command = '/bin/sh -c "/tmp/resources_generator.py --net {}{}{}{}{} -f"'.format(
        all_net,
        compute_cores_cmd,
        drive_cores_cmd,
        frontend_cores_cmd,
        memory_cmd,
    )
    logger.debug('Running Resources generator')
    run_shell_command(resource_generator_command)

    logger.debug('Releasing old hugepages allocation')
    path_to_huge = '/opt/weka/data/agent/containers/state/{}/huge'.format(container_name)
    path_to_huge1g = '/opt/weka/data/agent/containers/state/{}/huge1G'.format(container_name)
    if os.path.exists(path_to_huge) or os.path.exists(path_to_huge1g):
        find_and_remove_cmd = '/bin/sh -c "{}find {}* -name weka_* -delete"'.format(sudo, path_to_huge)
        run_shell_command(find_and_remove_cmd)
    logger.debug('Starting new containers')
    for container_type in ContainerType:
        if container_type == ContainerType.FRONTEND and frontend_cores == 0:
            continue
        setup_host_command = '/bin/sh -c "{}weka local setup host --resources-path={} {} {} {} --disable"'.format(
            sudo,
            container_type.json_name(),
            failure_domain,
            management_ips,
            join_ips
        )
        logger.debug("Starting container of type {} using the following command: {}".format(
            container_type.name, setup_host_command))
        run_shell_command(setup_host_command)

    # check if containers are up
    status_command = '/bin/sh -c "{}weka local status -J"'.format(sudo)
    local_status = {}
    for i in range(retries):
        local_status = json.loads(run_shell_command(status_command))
        if local_status[ContainerType.DRIVE.container_name()]['status']['internalStatus']['state'] == 'READY':
            break
    logger.debug('Waiting for drive containers to reach READY state, currently:{}'.format(
        local_status[ContainerType.DRIVE.container_name()]['status']['internalStatus']['state']))
    sleep(5)

    server_info = json.loads(run_shell_command(get_host_id_command))
    new_drive_host_id = server_info['hostIdValue']

    scan_disk_command = '/bin/sh -c "weka cluster drive scan {}"'.format(new_drive_host_id)
    run_shell_command(scan_disk_command)

    sleep(5)

    if protocols_in_host:
        get_resources_cmd = '/bin/sh -c "{}weka local resources -C {} -J"'.format(
            sudo,
            ContainerType.FRONTEND.container_name())
        frontend_resources = json.loads(run_shell_command(get_resources_cmd))
        get_host_id_command = '/bin/sh -c "weka debug manhole getServerInfo --slot=0 -P {}"' \
            .format(frontend_resources['base_port'])
        server_info = json.loads(run_shell_command(get_host_id_command))
        frontend_hostid = server_info['hostIdValue']
        for protocol in protocols_in_host:
            logger.debug("Adding {} protocol to frontend container".format(protocol.name))
            if protocol == Protocols.SMB:
                add_smb_host_cmd = '/bin/sh -c "weka smb cluster hosts add --samba-hosts {} -f"' \
                    .format(frontend_hostid)
                run_shell_command(add_smb_host_cmd)
            elif protocol == Protocols.S3:
                hosts_list = ''
                for k in s3_status.keys():
                    if int(extract_digits(k)) == current_host_id:
                        continue
                    hosts_list += extract_digits(k) + ','
                hosts_list += str(frontend_hostid)
                s3_update_command = '/bin/sh -c "weka s3 cluster update --host {}"'
                run_shell_command(s3_update_command.format(hosts_list))
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

    logger.debug('Starting cleanup')
    container_delete_command = '/bin/sh -c "{}weka local rm {} -f"'.format(sudo, container_name)
    run_shell_command(container_delete_command)
    container_delete_command = '/bin/sh -c "{}weka local enable"'.format(sudo)
    run_shell_command(container_delete_command)
    host_deactivate_command = '/bin/sh -c "weka cluster host deactivate {}"'.format(current_host_id)
    run_shell_command(host_deactivate_command)

    host_remove_command = '/bin/sh -c "weka cluster host remove {} --no-unimprint"'.format(current_host_id)
    run_shell_command(host_remove_command)

    for ct in ContainerType:
        if os.path.exists(ct.json_name()):
            os.remove(ct.json_name())
    if os.path.exists(backup_file_name):
        os.remove(backup_file_name)
    logger.debug('Finished cleanup')
    logger.debug("\nFinished moving host to MBC architecture")
    container_delete_command = '/bin/sh -c "{}weka local status -v"'.format(sudo)
    print(run_shell_command(container_delete_command).decode())


if '__main__' == __name__:
    main()
