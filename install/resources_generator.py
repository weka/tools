#!/usr/bin/env python3

###############################################################################
# DEPRECATION NOTICE:
# -------------------
# ⚠️  WARNING: OBSOLETE FILE ⚠️
# This file (install/resources_generator.py) is scheduled for removal.
# All modifications require a corresponding PR in the wekapp repository
# (Go implementation).
###############################################################################

import hashlib
import logging
import math
import os
import re
import sys
from argparse import ArgumentParser, HelpFormatter
from concurrent.futures import ThreadPoolExecutor
from json import dumps
from ipaddress import ip_address
from math import ceil
from urllib import request, error
from socket import AF_INET, AF_INET6, timeout
logging.basicConfig()
logger = logging.getLogger('resources generator')

DEFAULT_MAX_IO_NODES_PER_CONTAINER = 19
KB = 10 ** 3
MB = KB * 10 ** 3
GB = MB * 10 ** 3
TB = GB * 10 ** 3
PB = TB * 10 ** 3
KiB = 2 ** 10
MiB = KiB * 2 ** 10
GiB = MiB * 2 ** 10
TiB = GiB * 2 ** 10
PiB = TiB * 2 ** 10
UINT_MAX = 4294967295
DEFAULT_SPARE_CPU_ID = 0
IS_NUMA_PARTITION = len(os.popen("cat /sys/devices/system/node/possible").read().split("-")) > 1
IS_SINGLE_CORE = int(os.popen("nproc").read().strip()) == 1  # TODO: validate condition sufficiency
# Memory consts (from hugepages.d):
WEKANODE_BUCKET_PROCESS_MEMORY = 3.9 * GiB
WEKANODE_SSD_PROCESS_MEMORY = 2.2 * GiB
WEKANODE_FRONTEND_PROCESS_MEMORY = 2.3 * GiB
WEKANODE_MANAGER_PROCESS_MEMORY = 2.1 * GiB

OVERHEAD_PER_MBUF = 202 + 72 + 16 + 30  # GenericBaseBlock + QueuedBlock + Cache entries + unknown respectively
MBUFS_IN_HUGEPAGE = 481  # max N such that `align4K(256*N) + 4096*N <= 2MB
OVERHEAD_PER_HUGEPAGE = OVERHEAD_PER_MBUF * MBUFS_IN_HUGEPAGE
PAGE_2M_SIZE = 2 * MiB
HUGEPAGE_SIZE_BYTES = PAGE_2M_SIZE
DPDK_MEM_PER_NODE = 2 * MiB
DEFAULT_DRIVE_NODE_HUGEPAGES_MEMORY_BYTES = 1.4 * GiB
DEFAULT_FE_NODE_HUGEPAGES_MEMORY_BYTES = 1.4 * GiB
DEFAULT_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES = 1.4 * GiB
MIN_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES = 0.8 * GiB
MIN_OS_RESERVED_MEMORY = 8 * GiB
FRONTEND_ROLE = "FRONTEND"
DRIVE_ROLE = "DRIVES"
COMPUTE_ROLE = "COMPUTE"
MANAGEMENT_ROLE = "MANAGEMENT"
DEFAULT_DRIVES_BASE_PORT = 14000
TALKER_PORT = 15000
CONST_RESOURCES = dict(
    allow_unsupported_nics=False,
    auto_discovery_enabled=True,
    auto_remove_timeout=0,
    backend_endpoints=[],
    bandwidth=0,
    cpu_governor="PERFORMANCE",
    dedicate_memory=True,
    disable_numa_balancing=True,
    drives=[],
    failure_domain="",
    format=3,
    hardware_watchdog=False,
    host_id=65535,
    hostname="",
    ignore_clock_skew=False,
    ips=["127.0.0.1"],
    join_secret=[],
    mask_interrupts=True,
    memory=0,
    mode="BACKEND",
    net_devices=[],
    rdma_devices=dict(),
    ena_llq=True,
)
MAX_DRIVE_NODES_PERCPU = 4

def is_cloud_env(check_aws=True, check_oci=True):
    req_list = []
    if check_aws:
        headers = {"X-aws-ec2-metadata-token-ttl-seconds": "1"}
        req_list.append(request.Request("http://169.254.169.254/latest/api/token", headers=headers, method='PUT'))
    if check_oci:
        req_list.append(request.Request('http://169.254.169.254/opc/v2/instance/', headers={"Authorization": "Bearer Oracle"}))

    def _send_request(req):
        retries = 4
        init_timeout = 0.1
        for i in range(retries):
            try:
                request.urlopen(req, timeout=i * init_timeout).read()
                return True
            except error.URLError:
                pass
            except timeout:
                pass
            except ConnectionResetError:
                pass
        return False

    with ThreadPoolExecutor() as executor:
        return any(executor.map(_send_request, req_list))


def extract_digits(s):
    return "".join(filter(str.isdigit, s))


MAC_TO_NICS_MAP = dict()
with os.scandir('/sys/class/net/') as nets:
    for net in nets:
        net_addr_path = '/sys/class/net/%s/address' % net.name
        net_master_path = '/sys/class/net/%s/master' % net.name
        if net.name != 'lo' and os.path.isfile(net_addr_path):
            try:
                with open(net_addr_path) as file:
                    mac = file.read().replace('\n', '')
                    MAC_TO_NICS_MAP[net.name] = {'mac': mac}
            except OSError:
                logger.warning(
                    "Couldn't get hardware address for %s, skipping" % net.name
                )
                continue
            if os.path.islink(net_master_path):
                MAC_TO_NICS_MAP[net.name]['master'] = os.readlink(
                        net_master_path).split('/')[-1]

MACS = []
for name in MAC_TO_NICS_MAP:
    for mac in MAC_TO_NICS_MAP[name]:
        MACS.append(MAC_TO_NICS_MAP[name]['mac'])


def _is_mac_address(mac):
    if re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', mac):
        return True
    return False

def _is_pci_address(pci):
    pci_pattern = r'[0-9a-fA-F]{0,4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}.[0-9a-fA-F]'
    if re.fullmatch(pci_pattern, pci):
        return True
    return False

def _is_slave(name):
    if 'master' in MAC_TO_NICS_MAP[name]:
        return True

class NetDevice:
    def __init__(self, name, **kwargs):
        extract_pci_cmd = "/sbin/ethtool -i {nic} | grep bus-info".format(nic=name)
        pci_address = os.popen(extract_pci_cmd).read().strip().split(": ")[-1]
        self.device = pci_address if _is_pci_address(pci_address) and not kwargs.get('use_only_nic_identifier', False) else name
        self.gateway = kwargs.get('gateway', "")
        self.identifier = kwargs.get('identifier', self.device)
        self.ips = kwargs.get('ips', [])
        self.name = name
        self.netmask = kwargs.get('netmask', 0)
        self.network_label = kwargs.get('network_label', '')
        self.slots = kwargs.get('slots', [])
        self.rdma_only = kwargs.get('rdma-only', False)
        self.sa_family = kwargs.get('sa_family', AF_INET)

    def as_dict(self):
        return self.__dict__


class RdmaDevice:
    def __init__(self, name, sa_family):
        self.name = name
        self.sa_family = sa_family

    def as_dict(self):
        return self.__dict__

class Node:
    def __init__(self,
                 dedicate_core=True,
                 dedicated_mode="FULL",
                 core_id=UINT_MAX,
                 http_port=0,
                 rpc_port=0
                 ):
        self.core_id = core_id
        self.dedicate_core = dedicate_core
        self.dedicated_mode = dedicated_mode
        self.http_port = http_port
        self.roles = []
        self.rpc_port = rpc_port

    def is_compute(self):
        return COMPUTE_ROLE in self.roles

    def is_frontend(self):
        return FRONTEND_ROLE in self.roles

    def is_drive(self):
        return DRIVE_ROLE in self.roles

    def as_dict(self):
        return self.__dict__


class Core:
    def __init__(self, cpu_id=None):
        self.cpu_id = cpu_id
        self.numa = "-1"

    def set_numa(self):
        assert self.cpu_id is not None, "cpu_id must be set before detecting NUMA"
        get_numa_cmd = "ls /sys/devices/system/cpu/cpu{cpu_id} | grep -Eo 'node[[:digit:]]'".format(cpu_id=self.cpu_id)
        numa_node_str = os.popen(get_numa_cmd).read()
        self.numa = extract_digits(numa_node_str)


class Container:
    def __init__(self, memory=None, base_port=None, failure_domain=""):
        self.allow_protocols = False
        self.base_port = base_port
        self.drives = []
        self.memory = memory
        self.nodes = dict()
        self.net_devices = []
        self.rdma_devices = dict()
        self.resources_json = None
        self.failure_domain = failure_domain
        self.hostname = os.uname().nodename

    def prepare_members(self):
        self.nodes = {slot_id: self.nodes[slot_id].as_dict() for slot_id in self.nodes}
        self.net_devices = [dev.as_dict() for dev in self.net_devices]
        self.rdma_devices = dict(
            devicesValid = ResourcesGenerator.scan_rdma != 'OFF' or len(self.rdma_devices) > 0,
            devices = [rdma.as_dict() for rdma in self.rdma_devices],
            rdma_scan = ResourcesGenerator.scan_rdma,
        )

    def create_json(self):
        resources_dict = CONST_RESOURCES.copy()
        resources_dict.update(self.__dict__.copy())
        resources_dict.pop("resources_json")
        self.resources_json = dumps(resources_dict, sort_keys=True, indent=1)


def get_failure_domain_based_on_nodename():
    max_failure_domain_length = 16
    full_hostname = os.uname().nodename
    hostname = full_hostname.split('.')[0].replace('-', '_')  # just in case it's a FQDN
    if len(hostname) > max_failure_domain_length:
        hash_obj = hashlib.shake_256(hostname.encode())
        hostname = hash_obj.hexdigest(max_failure_domain_length // 2)
    return hostname


class Numa:
    def __init__(self, node_id):
        self.id = node_id
        self.pre_allocated_cores = []
        self.io_nodes = []
        self.memory = 0


class ResourcesGenerator:
    scan_rdma = 'OFF'
    def __init__(self):
        self.num_containers_by_role = dict()
        self.default_num_frontend_nodes = 1
        self.args = None
        self.net_devices = []
        self.rdma_devices = []
        self.drives = []
        self.num_available_cores = None
        self.all_available_cpus = None
        self.containers = dict()
        self.frontend_nodes = []
        self.drive_nodes = []
        self.compute_nodes = []
        self.cores = []
        self.numa_to_ionodes = dict()
        self.numa_nodes_info = []
        self.exclusive_nics_policy = None
        self.is_DEFAULT_DRIVES_BASE_PORT_used = False

    def set_user_args(self):
        """parses command line arguments"""
        def _validate_positive(value):
            int_val = int(value)
            if int_val <= 0:
                logger.error("%s is an invalid positive int value" % value)
                quit(1)
            return int_val

        def _validate_cores_per_container(value):
            int_val = int(value)
            if int_val not in range(1, DEFAULT_MAX_IO_NODES_PER_CONTAINER + 1):
                logger.error("--max-cores-per-container is expecting an int value between 1 and %s" % DEFAULT_MAX_IO_NODES_PER_CONTAINER)
                quit(1)
            return int_val

        def _validate_non_negative(value):
            int_val = int(value)
            if int_val < 0:
                logger.error("%s is an invalid non negative int value" % value)
                quit(1)
            return int_val

        def _validate_path(p):
            if not os.path.isdir(p):
                logger.error("Path argument must be a directory")
                quit(1)
            return p

        def _verify_core_ids(core_ids):
            for core_id in core_ids:
                if core_ids.count(core_id) > 1:
                    logger.error("CPU id: %s was passed multiple times" % core_id)
                    quit(1)
                if not os.path.isdir("/sys/devices/system/cpu/cpu{cpu_id}".format(cpu_id=core_id)):
                    logger.error("Could not find core id %s", core_id)
                    quit(1)
                _validate_non_negative(core_id)
            return core_ids

        def _verify_compatible_num_cores():
            if self.args.num_cores and self.args.core_ids:
                if self.args.num_cores != len(self.args.core_ids):
                    logger.error("The amount of cores requested (%s) is not equal to the number of specified core-ids (%s)",
                                 self.args.num_cores, len(self.args.core_ids))
                    quit(1)

        def _extract_nic_name(net_arg):
            ''' in some cases (i.e., LACP), self.args.net passes virtual interfaces (i.e., bond0:0)
            split(':') ensuring that both virtual and physical interfaces point to the same NIC '''
            nic_part = net_arg.split('/')[0]
            if _is_mac_address(nic_part):
                return nic_part
            else:
                return nic_part.split(':')[0]

        def _validate_net_dev():
            missing_nics = []
            nic_names = []
            nic_error = False

            if not self.args.net:
                logger.error("At least 1 net device is required")
                quit(1)
            nics = [_extract_nic_name(net_arg) for net_arg in self.args.net]

            for nic in nics:
                # Check if NICs are present on the machine
                if not (nic in MAC_TO_NICS_MAP.keys() or nic in MACS):
                    missing_nics.append(nic)
                    continue

                # If MAC address provided, convert to NIC name, selecting bond
                # interface (master) if present
                elif _is_mac_address(nic):
                    for name in MAC_TO_NICS_MAP:
                        if MAC_TO_NICS_MAP[name]['mac'] == nic \
                        and 'master' not in MAC_TO_NICS_MAP[name]:
                            nic_names.append(name)
                            break
                else:
                    nic_names.append(nic)

            # Check for NICs passed multiple times
            present_dupe_nics = {nic for nic in nic_names if
                    nic_names.count(nic) > 1}
            missing_dupe_nics = {nic for nic in missing_nics if
                    missing_nics.count(nic) > 1}

            # Set error mode and print detected NICs
            if len(present_dupe_nics) > 0 or len(missing_dupe_nics) > 0 \
                    or len(missing_nics) > 0:
                nic_error = True
                logger.error("Detected net devices: %s", MAC_TO_NICS_MAP)

            # Print duplicated NICs passed as arguments
            if len(present_dupe_nics) > 0:
                logger.error('Detected NICs were passed multiple times: %s'
                        % present_dupe_nics)
            if len(missing_dupe_nics) > 0:
                logger.error('Missing NICs were passed multiple times: %s'
                        % missing_dupe_nics)

            missing_nics = set(missing_nics)  # To strip duplicates
            if len(missing_nics) > 0:
                logger.error('Missing NICs were passed: %s' % missing_nics)

            if nic_error:
                quit(1)

        def _validate_scan_rdma(layer):
            if layer not in ['IB', 'ETH', 'ALL', 'OFF']:
                logger.error("scan-rdma can only be 'IB', 'ETH', 'ALL' or 'OFF")
                quit(1)

            return layer


        def _parse_pretty_bytes(size):
            units = dict(
                B=1,
                KIB=KiB,
                MIB=MiB,
                GIB=GiB,
                TIB=TiB,
                PIB=PiB,
                KB=KB,
                MB=MB,
                GB=GB,
                TB=TB,
                PB=PB,
            )
            def _is_num(val):
                try:
                    float(val)
                    return True
                except ValueError:
                    return False

            vals = re.split("(\d+)", size.strip())
            number = "".join(vals[:-1])
            unit_lst = list(filter(lambda s: s.isalpha(), vals))
            unit = unit_lst[0] if unit_lst else 'B'
            if not _is_num(number):
                logger.error("Invalid numeric value: %s", number)
                quit(1)
            if unit.upper() not in units:
                logger.error("Unknown unit: %s", unit)
                quit(1)
            return int(float(number) * units[unit.upper()])

        def _validate_memory_size(value):
            size = _parse_pretty_bytes(value)
            _validate_non_negative(size)
            return size

        class SortingHelpFormatter(HelpFormatter):
            def add_arguments(self, actions):
                actions = sorted(actions, key=lambda a: a.option_strings)
                super(SortingHelpFormatter, self).add_arguments(actions)

        parser = ArgumentParser(description="Generates weka resources files",
                                usage='\n%(prog)s --net <net-devices> [options]',
                                formatter_class=SortingHelpFormatter)
        parser.add_argument("--net", nargs="+", type=str, metavar="net-devices",
                            help="Specify net devices to be used separated by whitespaces")
        parser.add_argument("--drives", nargs="+", type=str,
                            help="Specify drives to be used separated by whitespaces (override automatic detection)")
        parser.add_argument("-v", "--verbose", action="count", default=0,
                            help="Sets console log level to DEBUG")
        parser.add_argument("-f", "--force", action="count", default=0,
                            help="Force continue in cases of prompts")
        parser.add_argument("--minimal-memory", action="count", default=0,
                            help="Set each container hugepages memory to %s GiB * number of io nodes on the container" %
                                 (MIN_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES / GiB))
        parser.add_argument("--spare-cores", default=1, type=_validate_non_negative,
                            help="Specify how many cores to leave for OS and non weka processes")
        parser.add_argument("--drive-dedicated-cores", default=None, type=_validate_non_negative,
                            help="Specify how many cores will be dedicated for DRIVE nodes")
        parser.add_argument("--frontend-dedicated-cores", default=None, type=_validate_non_negative,
                            help="Specify how many cores will be dedicated for FRONTEND nodes")
        parser.add_argument("--compute-dedicated-cores", default=None, type=_validate_non_negative,
                            help="Specify how many cores will be dedicated for COMPUTE nodes")
        parser.add_argument("--num-cores", default=None, type=_validate_positive,
                            help="Override the auto-deduction of number of cores")
        parser.add_argument("--max-cores-per-container", default=DEFAULT_MAX_IO_NODES_PER_CONTAINER, type=_validate_cores_per_container,
                            help="Override the default max number of cores per container: %s, if provided - new value must be lower" % DEFAULT_MAX_IO_NODES_PER_CONTAINER)
        parser.add_argument("--no-rdma", action='store_true',
                            help="Don't take RDMA support into account when computing memory requirements, false by default")
        parser.add_argument("--use-auto-failure-domain", action='store_true',
                            help="Use auto failure domain. Default is user defined based on node")
        parser.add_argument("--allow-all-disk-types", action='store_true',
                            help="Detect all available (non-rotational) devices. If not specified, only NVME devices will be detected. "
                                 "For allowing rotating disks - please add '--allow-rotational' as well")
        parser.add_argument("--allow-rotational", action='store_true',
                            help="Detect rotational disks")
        parser.add_argument("--core-ids", default=[], nargs='+', type=int,
                            help="Specify manually which CPUs to allocate for weka nodes")
        parser.add_argument("--compute-core-ids", default=[], nargs='+', type=int,
                            help="Specify manually which CPUs to allocate for COMPUTE nodes")
        parser.add_argument("--drive-core-ids", default=[], nargs='+', type=int,
                            help="Specify manually which CPUs to allocate for DRIVE nodes")
        parser.add_argument("--frontend-core-ids", default=[], nargs='+', type=int,
                            help="Specify manually which CPUs to allocate for FRONTEND nodes")
        parser.add_argument("--spare-memory", default=0, type=_validate_memory_size,
                            help="Specify how much memory should be reserved for non-weka requirements, "
                                 "argument should be value and unit without whitespace (i.e 10GiB, 1024B, 5TiB etc.)")
        parser.add_argument("--protocols-memory", default=0, type=_validate_memory_size,
                            help="Specify how much memory should be reserved for Protocols requirements, "
                                 "argument should be value and unit without whitespace (i.e 10GiB, 1024B, 5TiB etc.)")
        parser.add_argument("--compute-memory", default=0, type=_validate_memory_size,
                            help="Specify how much total memory should be allocated for COMPUTE, "
                                 "argument should be value and unit without whitespace (i.e 10GiB, 1024B, 5TiB etc.)")
        parser.add_argument("--weka-hugepages-memory", default=0, type=_validate_memory_size,
                            help="Specify how much memory should be allocated for COMPUTE, FRONTEND and DRIVE nodes."
                                 "argument should be value and unit without whitespace (i.e 10GiB, 1024B, 5TiB etc.)")
        parser.add_argument("--path", default=".", type=_validate_path,
                            help="Specify the directory path to which the resources files will be written, default is '.'")
        parser.add_argument("--use-only-nic-identifier", action='store_true', dest='use_only_nic_identifier',
                            help="use only the nic identifier when allocating the nics")
        parser.add_argument("--base-port", default=DEFAULT_DRIVES_BASE_PORT, type=int, help="Specify the base port")
        parser.add_argument("--scan-rdma", default="OFF", type=_validate_scan_rdma,
                            help="Scan for RDMA devices by network type, either 'IB', 'ETH', 'ALL' or 'OFF' (default)")

        # Create a mutually exclusive group
        group = parser.add_mutually_exclusive_group()

        group.add_argument(
            "--allocate-nics-exclusively", action='store_true',
            help="Set one unique net device per each io node, relevant when using virtual functions (VMware, KVM etc.)")

        group.add_argument(
            "--dont-allocate-nics-exclusively", action='store_true',
            help="Do not set one unique net device per each IO node"
        )

        self.args = parser.parse_args()

        if self.args.dont_allocate_nics_exclusively:
            self.exclusive_nics_policy = False
        else:
            self.exclusive_nics_policy = is_cloud_env() or self.args.allocate_nics_exclusively

        ResourcesGenerator.scan_rdma = self.args.scan_rdma
        self.next_base_port = self.args.base_port + 200

        _validate_net_dev()
        _verify_core_ids(self.args.drive_core_ids + self.args.compute_core_ids + self.args.frontend_core_ids)
        _verify_core_ids(self.args.core_ids)
        _verify_compatible_num_cores()

    def check_if_should_continue(self):
        if self.args.force:
            return
        inp = None
        while inp not in ['n', 'y', 'N', 'Y']:
            inp = input("Would you like to continue? (y/n) ")
            if inp in ['n', 'N']:
                quit(1)
            elif inp in ['y', 'Y']:
                return

    def _get_next_base_port(self, role):
        if role == DRIVE_ROLE and not self.is_DEFAULT_DRIVES_BASE_PORT_used:
            self.is_DEFAULT_DRIVES_BASE_PORT_used = True
            return self.args.base_port
        else:
            current_port = self.next_base_port
            self.next_base_port += 100
            if self.next_base_port == TALKER_PORT:
                self.next_base_port += 1000
            return current_port

    def _set_containers(self, role):
        if role == FRONTEND_ROLE:
            nodes = self.frontend_nodes[:]
        elif role == DRIVE_ROLE:
            nodes = self.drive_nodes[:]
        else:
            nodes = self.compute_nodes[:]
        failure_domain = "" if self.args.use_auto_failure_domain else get_failure_domain_based_on_nodename()

        num_nodes = len(nodes)
        num_containers = self.num_containers_by_role[role]
        average_nodes_per_container = int(num_nodes / num_containers)
        logger.debug(f"average nodes per container for {role}: {average_nodes_per_container}")
        num_nodes_by_container = dict()     # key is container number

        # are there leftover nodes? (ie: the containers will have uneven numbers of cores)
        nodes_per_average = average_nodes_per_container * num_containers
        extra_nodes = 0
        if nodes_per_average != num_nodes:
            extra_nodes = num_nodes - nodes_per_average

        for i in range(self.num_containers_by_role[role]):
            num_nodes_by_container[i] = average_nodes_per_container
            num_nodes -= average_nodes_per_container
            if i < extra_nodes:
                num_nodes_by_container[i] += 1
                num_nodes -= 1

        for container_no, num_nodes in num_nodes_by_container.items():
            logger.debug(f"container {container_no}: {num_nodes}")

        for i in range(self.num_containers_by_role[role]):
            slot_id = 0
            base_port = self._get_next_base_port(role)
            container = Container(base_port=base_port, failure_domain=failure_domain)
            mgmt_node = Node(dedicate_core=False, http_port=base_port, rpc_port=base_port)
            mgmt_node.roles.append(MANAGEMENT_ROLE)
            container.nodes[str(slot_id)] = mgmt_node
            while nodes and slot_id < num_nodes_by_container[i]:
                slot_id += 1
                node = nodes.pop()
                node.http_port = base_port
                node.rpc_port = node.http_port + slot_id
                container.nodes[str(slot_id)] = node
                container.allow_protocols = role == FRONTEND_ROLE
            if self.exclusive_nics_policy:
                # in cloud env every io node has to be served by an exclusive net device,
                # therefor we'll count the io nodes in the current container (all nodes except one MGMT)
                # and then pop one net device for each node and associate it with its container.
                io_nodes_counter = len(container.nodes) - 1
                for i in range(io_nodes_counter):
                    nic = self.net_devices.pop()
                    container.net_devices.append(nic)
            else:
                container.net_devices = self.net_devices[:]
                container.rdma_devices = self.rdma_devices[:]
            self.containers[role].append(container)
            logger.info("Added %s container resources", role)

    def _init_num_containers_by_role(self):
        nodes_per_roles = zip([self.frontend_nodes, self.drive_nodes, self.compute_nodes], [FRONTEND_ROLE, DRIVE_ROLE, COMPUTE_ROLE])
        for nodes, role in nodes_per_roles:
            nodes_count = len(nodes)
            num_containers = int(ceil(float(nodes_count) / self.args.max_cores_per_container))
            self.num_containers_by_role[role] = num_containers
            logger.info("num_containers_by_role[%s]: %s, nodes count: %s", role, num_containers, nodes_count)

    def _add_drives(self):
        drives_to_allocate = sorted(self.drives)
        num_drives = len(self.drives)

        # multiple drives containers make it more complicated
        total_drives_nodes = 0
        for container in self.containers[DRIVE_ROLE]:
            total_drives_nodes += len(container.nodes) -1

        drive_node_ratio = float(num_drives / total_drives_nodes)  # typically 1.0 or 2.0
        logger.info(f"drive_node_ratio = {drive_node_ratio}: {num_drives}/{total_drives_nodes}")

        while drives_to_allocate:
            logger.debug(f"{self.containers[DRIVE_ROLE]} drives: {self.drives}")
            for container in self.containers[DRIVE_ROLE]:
                num_drive_nodes = len(container.nodes) - 1
                num_drives_to_allocate = round(num_drive_nodes * drive_node_ratio)
                logger.debug(f"assigning {num_drives_to_allocate} drives to {num_drive_nodes} nodes with ratio: {drive_node_ratio}")
                drives_to_assign = drives_to_allocate[:int(num_drives_to_allocate)]  # make a subset
                logger.debug(f"assigning {drives_to_assign}")
                container.drives += [{"path": drive} for drive in drives_to_assign]
                drives_to_allocate = list(set(drives_to_allocate) - set(drives_to_assign))

    def _ensure_base_port_is_used(self):
        if not self.containers[DRIVE_ROLE] and self.containers[COMPUTE_ROLE]:
            self.containers[COMPUTE_ROLE][0].base_port = self.args.base_port
            for slot_id in range(len(self.containers[COMPUTE_ROLE][0].nodes)):
                self.containers[COMPUTE_ROLE][0].nodes[str(slot_id)].http_port = self.args.base_port
                self.containers[COMPUTE_ROLE][0].nodes[str(slot_id)].rpc_port = self.args.base_port + slot_id

    def set_containers(self):
        """Conclude how many containers needed of each type
        either from user's args or from default definitions
        and instantiate Container objects accordingly
        Set containers of types:
        Drives, Compute, Frontend (in the future - SMB, S3, Ganesha instead of Frontend)"""
        self._init_num_containers_by_role()
        for role in self.num_containers_by_role:
            self.containers[role] = []
            self._set_containers(role)
            if role == DRIVE_ROLE:
                self._add_drives()
        self._ensure_base_port_is_used()

    def set_net_devices(self):
        def _validate_ips(ip):
            try:
                ip_address(ip)
                return ip
            except ValueError as err:
                logger.error(err)
                quit(1)

        def _validate_netmask(netmask):
            if not netmask.isdecimal() or int(netmask) not in range(0, 129):
                logger.error("Invalid value for netmask: %s", netmask)
                quit(1)
            return netmask

        for net_arg in self.args.net:
            kwargs = dict()
            arg_parts = net_arg.split('/')
            name = arg_parts.pop(0)

            if arg_parts and arg_parts[0] == "rdma-only":
                if self.args.scan_rdma is not 'OFF':
                    logger.error("Mixing rdma-only and scan-rdma is not permitted")
                    quit(1)
                sa_family = AF_INET
                arg_parts.pop(0)
                if arg_parts and arg_parts[0] == "inet6":
                    sa_family = AF_INET6

                rdma_dev = RdmaDevice(name, sa_family)
                logger.debug("Added rdma device: %s", rdma_dev.__dict__)
                self.rdma_devices.append(rdma_dev)
                continue

            # If MAC address provided, convert to NIC name, selecting bond if
            # present. Note that this occurs in _validate_net_dev as well;
            # perhaps worth deduplicating this at some point in the future.
            if _is_mac_address(name):
                for nic_name in MAC_TO_NICS_MAP:
                    if MAC_TO_NICS_MAP[nic_name]['mac'] == name \
                    and 'master' not in MAC_TO_NICS_MAP[nic_name]:
                        name = nic_name
                        break

            # Otherwise, if NIC name provided, check if slave and select its
            # master (bond) instead. Note that this isn't validated in
            # _validate_net_dev; these functions should perhaps be incorporated
            # together in the future.
            elif _is_slave(name):
                logger.warning('Selecting %s as %s (%s) is slave device of %s'
                        % (MAC_TO_NICS_MAP[name]['master'], name,
                            MAC_TO_NICS_MAP[name]['mac'],
                            MAC_TO_NICS_MAP[name]['master']))
                name = MAC_TO_NICS_MAP[name]['master']
            if arg_parts:
                ips = arg_parts.pop(0).split('+')
                ips = list(map(_validate_ips, ips))
                kwargs['ips'] = [ip.strip() for ip in ips]
            if arg_parts:
                net_mask_arg = arg_parts.pop(0)
                _validate_netmask(net_mask_arg)
                kwargs['netmask'] = int(net_mask_arg)
            if arg_parts:
                gateway = arg_parts.pop(0)
                if len(gateway) > 0:
                    _validate_ips(gateway)
                    kwargs['gateway'] = gateway
            if arg_parts:
                network_label = arg_parts.pop(0)
                kwargs['network_label'] = network_label
            kwargs['use_only_nic_identifier'] = self.args.use_only_nic_identifier
            net_dev = NetDevice(name=name, **kwargs)
            logger.debug("Added net device: %s", net_dev.__dict__)
            self.net_devices.append(net_dev)

    def _get_all_cpus(self):
        cpu_ids_str = re.findall('cpu\d+', os.popen("ls /sys/devices/system/cpu").read())
        return [int(extract_digits(cpu_str)) for cpu_str in cpu_ids_str]

    def _get_siblings_cpus(self):
        cmd = "cat /sys/devices/system/cpu/cpu*/topology/thread_siblings_list"
        cpu_pairs_ids = set(os.popen(cmd).read().strip().splitlines())
        logger.debug("cpu_pairs_ids before removing siblings: %s", cpu_pairs_ids)
        cpu_per_core = [int(re.split(',|-', pair)[0]) for pair in cpu_pairs_ids]
        return cpu_per_core

    def set_numa_nodes_info(self):
        def _get_numa_total_memory_bytes(n_id):
            return int(extract_digits(
                os.popen("cat /sys/devices/system/node/node{node_id}/meminfo | grep -Eo 'MemTotal: *[0-9]* kB'".format(
                    node_id=n_id)).read().strip())) * KiB

        numa_nodes = os.popen("ls /sys/devices/system/node | grep -Eo 'node[0-9]{1,2}'").read().strip().splitlines()
        numa_nodes_ids = [extract_digits(numa) for numa in numa_nodes]
        for numa_node_id in numa_nodes_ids:
            numa = Numa(numa_node_id)
            numa.pre_allocated_cores = list(filter(lambda c: c.numa == numa_node_id, self.cores))
            numa.memory = _get_numa_total_memory_bytes(numa_node_id)
            self.numa_nodes_info.append(numa)
            self.numa_to_ionodes[numa_node_id] = []
            logger.info("NUMA %s cores: %s, total memory: %s GiB",
                        numa_node_id,
                        [c.cpu_id for c in numa.pre_allocated_cores],
                        numa.memory / GiB)

    def _verify_cpu0_not_included(self, core_ids):
        if DEFAULT_SPARE_CPU_ID in core_ids:
            logger.warning("cpu 0 was found among specified core ids, that is highly unrecommended")
            self.check_if_should_continue()

    def _verify_at_least_one_spare_cores(self, core_ids):
        if len(core_ids) == len(self.all_available_cpus):
            logger.warning(
                "no spare cores were left for the os, consider allocate less cores for wekanodes if possible")
            self.check_if_should_continue()

    def _validate_spare_cores(self):
        if self.args.spare_cores > len(self.all_available_cpus):
            logger.error("the specified spare-corse value is greater than the total number of available cores")
            quit(1)

    def set_cores(self):
        """Get 1 cpu id and the relevant NUMA node per each required core, init Core objects"""
        specified_num_cores = self.args.num_cores
        self.all_available_cpus = self._get_siblings_cpus()
        self._validate_spare_cores()
        if self.args.core_ids:  # user specified cpu ids
            usable_cpus = self.args.core_ids[:]
            self._verify_cpu0_not_included(usable_cpus)
            self._verify_at_least_one_spare_cores(usable_cpus)
            specified_num_cores = len(self.args.core_ids)
        else:
            usable_cpus = self.all_available_cpus[:]
            should_reserve_core_0 = not IS_SINGLE_CORE and self.args.spare_cores != 0
            if should_reserve_core_0:
                usable_cpus.remove(DEFAULT_SPARE_CPU_ID)
        self.num_available_cores = specified_num_cores if specified_num_cores else (len(self.all_available_cpus) - self.args.spare_cores)
        logger.debug("num available cores: %s", self.num_available_cores)
        logger.debug("num-cores specified by user: %s", self.args.num_cores)
        logger.debug("spare cores: %s", self.args.spare_cores)
        if specified_num_cores:
            cores_available_for_weka = len(self.all_available_cpus) - self.args.spare_cores
            if specified_num_cores > cores_available_for_weka:
                msg = "not enough cores for allocating %s as requested (available: %s), "\
                      "consider either specifying less or decreasing spare-cores"
                logger.error(msg, specified_num_cores, cores_available_for_weka)
                quit(1)

        self.cores = [Core(cpu_id=cpu_id) for cpu_id in usable_cpus]

        for core in self.cores:
            core.set_numa()

    def set_specified_cores(self):
        available_cpus = self._get_all_cpus()
        for core_id in self.args.frontend_core_ids + self.args.compute_core_ids + self.args.drive_core_ids:
            if core_id not in available_cpus:
                logger.error("Core id: %s was not found, please make sure to pass values from the following available"
                             "CPUS: \n%s", core_id, sorted(available_cpus))
                quit(1)
            core = Core(cpu_id=core_id)
            core.set_numa()
            self.cores.append(core)

    def set_nodes_by_specified_cores(self):
        frontend_cores = list(filter(lambda c: c.cpu_id in self.args.frontend_core_ids, self.cores))
        compute_cores = list(filter(lambda c: c.cpu_id in self.args.compute_core_ids, self.cores))
        drive_cores = list(filter(lambda c: c.cpu_id in self.args.drive_core_ids, self.cores))
        roles_cores = zip((FRONTEND_ROLE, DRIVE_ROLE, COMPUTE_ROLE),
                          (frontend_cores, drive_cores, compute_cores))

        for role, cores in roles_cores:
            logger.info("ROLE: %s, CPU ids: %s", role, [c.cpu_id for c in cores])
            for core in cores:
                node = Node(core_id=core.cpu_id)
                node.roles.append(role)
                if role == DRIVE_ROLE:
                    self.drive_nodes.append(node)
                elif role == COMPUTE_ROLE:
                    self.compute_nodes.append(node)
                elif role == FRONTEND_ROLE:
                    self.frontend_nodes.append(node)
                self.numa_to_ionodes[core.numa].append(node)

    def set_nodes(self):
        """If not specified by user -
        allocates by default:
        one DRIVE core for each drive,
        one FRONTEND node in its own container (in the future - will run in the protocols' container),
        rest of the cores for COMPUTE NODES
        (except for cpu0 and its sibling, reserved for the OS)"""
        user_specified_core_ids = bool(self.args.core_ids)
        user_specified_num_cores = self.args.num_cores
        no_compute_by_request = self.args.compute_dedicated_cores == 0
        net_devs_counter = len(self.net_devices)
        if user_specified_num_cores:
            if self.exclusive_nics_policy and user_specified_num_cores > net_devs_counter:
                logger.error("Not enough net devices to serve %s nodes, maximum possible: %s",
                             user_specified_num_cores, net_devs_counter)
                quit(1)
        num_drive_nodes = self.args.drive_dedicated_cores if self.args.drive_dedicated_cores is not None else len(self.drives)
        num_frontend_nodes = self.args.frontend_dedicated_cores if self.args.frontend_dedicated_cores is not None else self.default_num_frontend_nodes
        available_cores_counter = self.num_available_cores if not self.exclusive_nics_policy else min(self.num_available_cores, len(self.net_devices))
        available_cores_counter = user_specified_num_cores if user_specified_num_cores else available_cores_counter
        default_num_compute_nodes = available_cores_counter - (num_drive_nodes + num_frontend_nodes)  # TODO: WEKAPP-247201
        drive_nodes_per_core = 1
        grouped_drive_nodes = num_drive_nodes
        while default_num_compute_nodes < 1:
             grouped_drive_nodes = math.floor(num_drive_nodes / (drive_nodes_per_core + 1)) + 1
             default_num_compute_nodes = available_cores_counter - (grouped_drive_nodes + num_frontend_nodes)
             drive_nodes_per_core = drive_nodes_per_core + 1
             if drive_nodes_per_core > MAX_DRIVE_NODES_PERCPU:
                  break
        default_num_compute_nodes = max(0, default_num_compute_nodes)
        num_compute_nodes = self.args.compute_dedicated_cores if self.args.compute_dedicated_cores is not None else default_num_compute_nodes
        weka_required_cores = grouped_drive_nodes + num_frontend_nodes + num_compute_nodes
        msg = f"\n{num_compute_nodes} {COMPUTE_ROLE},\n" \
              f"{num_frontend_nodes} {FRONTEND_ROLE},\n{num_drive_nodes} {DRIVE_ROLE}.\n" \
              f"Available net devices: {len(self.net_devices)}\nAvailable cores: {self.num_available_cores}"
        if weka_required_cores > available_cores_counter:
            prefix = f"Not enough resources to serve {weka_required_cores} nodes:"
            logger.error(prefix + msg)
            quit(1)
        if not no_compute_by_request and num_compute_nodes < 1:
            prefix = "Not enough resources for COMPUTE nodes:"
            logger.error(prefix + msg)
            quit(1)

        cores_to_allocate = []
        while len(cores_to_allocate) < weka_required_cores:
            for numa in self.numa_nodes_info:
                if numa.pre_allocated_cores:
                    core = numa.pre_allocated_cores.pop()
                    cores_to_allocate.append(core)

        def _get_next_node(role):
            next_core = cores_to_allocate.pop(0)
            node = Node(core_id=next_core.cpu_id)
            node.roles.append(role)
            self.numa_to_ionodes[next_core.numa].append(node)
            return node

        def _get_next_drive_node(index):
            if drive_nodes_per_core == 1:
                next_core = cores_to_allocate.pop(0)
            else:
                if (index+1) % drive_nodes_per_core == 0:
                    next_core = cores_to_allocate.pop(0)
                else:
                    next_core = cores_to_allocate[0]
            node = Node(core_id = next_core.cpu_id)
            node.roles.append(DRIVE_ROLE)
            self.numa_to_ionodes[next_core.numa].append(node)
            return node

        for i in range(num_frontend_nodes):
            self.frontend_nodes.append(_get_next_node(role=FRONTEND_ROLE))
        for i in range(num_compute_nodes):
            self.compute_nodes.append(_get_next_node(role=COMPUTE_ROLE))
        for i in range(num_drive_nodes):
            self.drive_nodes.append(_get_next_drive_node(i))

    def _get_total_memory_bytes(self):
        return int(extract_digits(os.popen("cat /proc/meminfo | grep MemTotal").read().strip())) * KiB

    def _get_os_reserved_memory(self, total_memory):
        min_ram_portion_denom = 50  # 2 % of total memory
        return max(total_memory / min_ram_portion_denom, MIN_OS_RESERVED_MEMORY)

    def _estimate_nodes_resident_memory_size(self, nodes=None):
        if nodes:
            compute_count = len([n for n in nodes if COMPUTE_ROLE in n.roles]) if nodes else len(self.compute_nodes)
            drive_count = len([n for n in nodes if DRIVE_ROLE in n.roles]) if nodes else len(self.drive_nodes)
            frontend_count = len([n for n in nodes if FRONTEND_ROLE in n.roles]) if nodes else len(self.frontend_nodes)
        else:
            compute_count = len(self.compute_nodes)
            drive_count = len(self.drive_nodes)
            frontend_count = len(self.frontend_nodes)
        mgmt_count = len(self.num_containers_by_role)
        logger.debug("_estimate_nodes_resident_memory_size: compute_count=%s, drive_count=%s, frontend=%s, mgmt_count=%s",
                     compute_count, drive_count, frontend_count, mgmt_count)
        return (compute_count * WEKANODE_BUCKET_PROCESS_MEMORY) + (drive_count * WEKANODE_SSD_PROCESS_MEMORY) + \
            (frontend_count * WEKANODE_FRONTEND_PROCESS_MEMORY) + \
            (mgmt_count * WEKANODE_MANAGER_PROCESS_MEMORY / len(self.numa_nodes_info))

    def _get_reserved_memory(self):
        """Return how many bytes cannot be allocated for wekanodes' hugepages"""
        #protocols_reserved_memory = 8 * GiB  # vince - This should be a parameter? (it's too small)
        RDMA_reserved_memory = 2 * GiB
        # max_reserved_portion_denom = 5  # 20% of total memory  (huh?)
        total_memory_bytes = self._get_total_memory_bytes()
        logger.debug("Total memory: %s MiB", total_memory_bytes / MiB)
        # total_reserve = auto_os_reserved_memory = self._get_os_reserved_memory(total_memory_bytes)
        total_reserve = auto_os_reserved_memory = MIN_OS_RESERVED_MEMORY
        if self.args.spare_memory:
            if self.args.spare_memory < auto_os_reserved_memory:
                logger.warning("The spare-memory requested: %s bytes is lower than the minimum recommended memory for this "
                               "machine: %s bytes", self.args.spare_memory, auto_os_reserved_memory)
                self.check_if_should_continue()
            total_reserve += self.args.spare_memory
        if self.args.protocols_memory:
            total_reserve += self.args.protocols_memory
            logger.debug(f'_get_reserved_memory: protocols memory {round(self.args.protocols_memory / GiB, 1)} GiB')

        #total_reserve = os_reserved_memory
        if not self.args.no_rdma:
            total_reserve += RDMA_reserved_memory
            logger.debug("_get_reserved_memory: reserving %s MiB for RDMA", RDMA_reserved_memory / MiB)
        #if not self.args.spare_memory and total_reserve > total_memory_bytes / max_reserved_portion_denom:
        #    fixed_total_reserve = total_memory_bytes / max_reserved_portion_denom   # vince- WRONG!  High-mem systems this is ok
        #    logger.warning("we need reserves of %s GiB which is too much (host has %s GiB), we'll settle with %s GiB reserved"
        #                   , total_reserve / GiB, total_memory_bytes / GiB, fixed_total_reserve / GiB)
        #    total_reserve = fixed_total_reserve
        logger.debug(f'_get_reserved_memory: total reserved memory {round(total_reserve / GiB, 1)} GiB')
        return total_reserve

    def _get_hugepages_memory_per_compute_node(self, numa_total_memory, io_nodes):
        wekanodes_memory_factor = 1.05
        num_compute_nodes = len([n for n in io_nodes if n.is_compute()])
        num_drive_nodes = len([n for n in io_nodes if n.is_drive()])
        num_fe_nodes = len([n for n in io_nodes if n.is_frontend()])
        logger.debug("_get_hugepages_memory_per_compute_node: num_compute_nodes: %s", num_compute_nodes)
        if num_compute_nodes == 0:
            logger.debug("_get_hugepages_memory_per_compute_node no compute nodes, will return 0")
            return 0
        wekanodes_memory = self._estimate_nodes_resident_memory_size(io_nodes) * wekanodes_memory_factor
        logger.debug("_get_hugepages_memory_per_compute_node WEKANODES RSS MEMORY: %s GiB", round(wekanodes_memory / GiB, 2))
        available = numa_total_memory - wekanodes_memory
        if available <= 0:
            logger.warning("_get_hugepages_memory_per_compute_node not enough available memory, will set memory to the minimal")
            return MIN_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES

        non_compute_nodes_hugepages_memory = DEFAULT_DRIVE_NODE_HUGEPAGES_MEMORY_BYTES * num_drive_nodes + DEFAULT_FE_NODE_HUGEPAGES_MEMORY_BYTES * num_fe_nodes
        logger.debug("_get_hugepages_memory_per_compute_node non_compute_nodes_hugepages_memory=%s GiB (%s non compute nodes)",
                     non_compute_nodes_hugepages_memory / GiB, num_drive_nodes+num_fe_nodes)

        available_for_compute = available - non_compute_nodes_hugepages_memory
        logger.debug("_get_hugepages_memory_per_compute_node: available_for_compute=%s GiB", available_for_compute / GiB)
        hugepages_count = available_for_compute / (HUGEPAGE_SIZE_BYTES + OVERHEAD_PER_HUGEPAGE)
        hugepages_memory = hugepages_count * HUGEPAGE_SIZE_BYTES
        per_compute_node_memory = hugepages_memory / num_compute_nodes
        logger.debug("_get_hugepages_memory_per_compute_node per_compute_node_memory=%s", per_compute_node_memory)
        return max(MIN_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES, per_compute_node_memory)

    def _get_compute_slot_memory_requirement(self):
        long_max = minimal_per_compute_node_memory = sys.maxsize
        numa_nodes_count = len(self.numa_nodes_info)
        total_reserved = self._get_reserved_memory()
        reserved_memory_per_numa = total_reserved / numa_nodes_count
        logger.debug("reserved memory: %s MiB", total_reserved / MiB)
        logger.debug("numa_nodes_count: %s", numa_nodes_count)
        logger.debug("reserved_memory_per_numa: %s MiB", reserved_memory_per_numa / MiB)
        for numa in self.numa_nodes_info:
            io_nodes_on_numa = self.numa_to_ionodes[numa.id]
            logger.info("%s io nodes on NUMA %s", len(io_nodes_on_numa), numa.id)
            numa_non_reserved_memory = numa.memory - reserved_memory_per_numa
            logger.debug("non-reserved memory on numa %s: %s MiB", numa.id, numa_non_reserved_memory / MiB)
            per_compute_node_memory = self._get_hugepages_memory_per_compute_node(numa.memory - reserved_memory_per_numa, io_nodes_on_numa)
            logger.debug("_get_compute_slot_memory_requirement: per_compute_node_memory: %s MiB, (numa %s)", per_compute_node_memory / MiB, numa.id)
            if per_compute_node_memory == 0:
                logger.debug("No compute nodes on NUMA %s", numa.id)
                continue
            minimal_per_compute_node_memory = min(minimal_per_compute_node_memory, per_compute_node_memory)

            if minimal_per_compute_node_memory <= DEFAULT_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES:
                # If the memory for compute nodes is already at the minimum, we can stop iterating
                logger.debug("NUMA %s minimal_per_compute_node_memory (%s GiB) is now at the minimum, stopping the search",
                             numa.id, minimal_per_compute_node_memory / GiB)
                break

        if minimal_per_compute_node_memory == long_max:
            # If no value was determined for some reason (e.g not enough memory on any numa)
            minimal_per_compute_node_memory = MIN_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES
        logger.debug("minimal_per_compute_node_memory=%sGiB = %sB", minimal_per_compute_node_memory / GiB, minimal_per_compute_node_memory)
        return int(minimal_per_compute_node_memory)

    def _get_validated_compute_memory_arg(self, specified_compute_memory):
        auto_compute_node_hugepages_memory = self._get_compute_slot_memory_requirement()
        compute_nodes_count = len(self.compute_nodes)
        compute_node_hugepages_memory = int(specified_compute_memory / compute_nodes_count)
        if compute_node_hugepages_memory > auto_compute_node_hugepages_memory:
            logger.warning("The specified memory per compute node is higher than the automatically computed value. "
                           "That might result in some lack of memory on 1 or more numa nodes for some containers")
            self.check_if_should_continue()
        available_memory = self._get_total_memory_bytes() - self._get_reserved_memory()
        if specified_compute_memory > available_memory:
            logger.warning(
                "Total requested memory for compute nodes: %s GiB is higher than available memory found on this server: %s GiB",
                specified_compute_memory, available_memory)
            self.check_if_should_continue()
        if compute_node_hugepages_memory <= 0:
            logger.error("Not enough memory for compute nodes")
            quit(1)
        if compute_node_hugepages_memory < DEFAULT_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES:
            logger.warning("The requested memory per compute node: %s GiB is lower than the default minimum: %s GiB",
                           compute_node_hugepages_memory / GiB, DEFAULT_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES / GiB)
            self.check_if_should_continue()
        return compute_node_hugepages_memory

    def _get_compute_mem_from_specified_total(self):
        non_compute_ionodes_counter = len(self.drive_nodes + self.frontend_nodes)
        logger.debug("non_compute_ionodes_counter: %s", non_compute_ionodes_counter)
        total_compute_memory = self.args.weka_hugepages_memory - (DEFAULT_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES * non_compute_ionodes_counter)
        logger.debug("weka total memory specified by user: %s GiB", self.args.weka_hugepages_memory / GiB)
        logger.debug("total_compute_memory: %s GiB", total_compute_memory / GiB)
        return total_compute_memory

    def set_memory(self):
        """Determine how much memory will be allocated for compute nodes, and set memory member of each container"""
        if self.containers[COMPUTE_ROLE]:
            if self.args.minimal_memory:
                if self.args.compute_memory:
                    logger.error("minimal-memory and compute-memory cannot be specified together")
                    quit(1)
                compute_node_hugepages_memory = DEFAULT_COMPUTE_NODE_HUGEPAGES_MEMORY_BYTES
            elif self.args.weka_hugepages_memory:
                compute_memory = self._get_compute_mem_from_specified_total()
                compute_node_hugepages_memory = self._get_validated_compute_memory_arg(compute_memory)
            else:
                compute_node_hugepages_memory = self._get_compute_slot_memory_requirement()
                if self.args.compute_memory:  # user specified compute-memory
                    compute_node_hugepages_memory = self._get_validated_compute_memory_arg(self.args.compute_memory)

        for role in self.containers:
            for container in self.containers[role]:
                if role == COMPUTE_ROLE:
                    compute_nodes_count = len(list(filter(lambda n: n.is_compute(), container.nodes.values())))
                    memory = compute_node_hugepages_memory * compute_nodes_count
                    container.memory = memory
                    logger.info("allocating %s GiB for %s container, (%s nodes)", memory / GiB, role, compute_nodes_count)
                else:
                    container.memory = 0

    def find_unmounted_devices(self):
        """Get all /dev/nvme* (or relevant oraclevd in OCI) devices on the machine that are not mounted anywhere"""
        all_mounted_devices = os.popen("cat /proc/mounts").read().strip().splitlines()
        all_mounted_devices_from_mount = os.popen("mount -l").read().strip().splitlines()
        all_mounted_devices += all_mounted_devices_from_mount
        swaps = os.popen("cat /proc/swaps").read().splitlines()[1:]

        def _is_nvme(dev):
            class_path = f"/sys/block/{dev}/device/device/class"
            nvme_controler = "0x010802"
            if os.path.isfile(class_path):
                if os.popen(f"cat {class_path}").read().strip() == nvme_controler:
                    return True
            return False

        def _is_relevant_device(dev):
            is_disk_type = dev[2] == 'disk'
            is_mounted = any(True for mounted_device in all_mounted_devices if dev[0] in mounted_device)
            is_swap = any(True for swap in swaps if dev[0] in swap)
            is_rotational = dev[1] == '1'
            ret = is_disk_type and not (is_mounted or is_swap)
            if not self.args.allow_all_disk_types:
                ret = ret and _is_nvme(dev[0])
            if not self.args.allow_rotational:
                ret = ret and not is_rotational
            return ret

        devices = [dev for dev in os.popen("lsblk -d -o name,rota,type").read().splitlines()]
        devices = [dev.split() for dev in devices[1:]]
        relevant_devices = [dev[0] for dev in devices if _is_relevant_device(dev)]
        self.drives = ["/dev/" + dev for dev in relevant_devices]
        self.drives.sort()
        logger.info("Drives to be allocated: %s", self.drives)

    def set_specified_drives(self):
        devices = ['/dev/' + dev for dev in os.popen("lsblk -d -o name").read().splitlines()[1:]]
        for dev in self.args.drives:
            if dev not in devices:
                logger.warning("Drive: %s was not found on the server", dev)
                logger.warning("Known devices: %s", devices)
                self.check_if_should_continue()
            #self.drives.append({"path": dev})
            self.drives.append(dev)
        logger.info("Drives to be allocated: %s", self.drives)

    def create_resources_files(self):
        """For each required container generates resources json file"""
        resources_filenames_path = os.path.join(self.args.path, "resources_filenames")
        with open(resources_filenames_path, 'w') as resources_filenames_file:
            for role in self.containers:
                for i, container in enumerate(self.containers[role]):
                    container.prepare_members()
                    container.create_json()
                    resources_path = os.path.join(self.args.path, role.lower() + str(i) + '.json')
                    with open(resources_path, 'w') as f:
                        f.write(container.resources_json + '\n')
                    resources_filenames_file.write(resources_path + '\n')

    def _setup_logging(self):
        logging.basicConfig(format='%(levelname)s: %(message)s')
        logger.setLevel(logging.DEBUG if self.args.verbose else logging.INFO)

    def generate(self):
        """Run the whole flow from parsing command-line arguments to generate all the required json files"""
        self.set_user_args()
        self._setup_logging()
        self.set_net_devices()
        if self.args.drives:
            self.set_specified_drives()
        else:
            self.find_unmounted_devices()
        use_auto_cores = not (self.args.frontend_core_ids or self.args.compute_core_ids or self.args.drive_core_ids)
        if use_auto_cores:
            self.set_cores()
            self.set_numa_nodes_info()
            self.set_nodes()

        else:
            self.set_specified_cores()
            self.set_numa_nodes_info()
            self.set_nodes_by_specified_cores()
        self.set_containers()
        self.set_memory()
        self.create_resources_files()


if __name__ == '__main__':
    rg = ResourcesGenerator()
    rg.generate()
