#!/usr/bin/env python3
import copy
import json
import random
import re
import subprocess

## preamble:
print(f"THIS IS THE BETA VERSION FOR Drives and Compute THIS IS NOT READY!")

## open initial file
with open ('original/drives0.json') as f:
        d = json.load(f)

## get nic name initial (may not be used)
net_dev0_name =  d['net_devices'][0]['name']
net_dev1_name =  d['net_devices'][1]['name']

## get ip -br a output
e = subprocess.check_output(['ip', '-j', 'a'])
g = json.loads(e)

## get nic names from system in case json is bad
dev_name0_ip_addr = g[1]['addr_info'][0]['local']
dev_name1_ip_addr = g[2]['addr_info'][0]['local']

## get inital file net_devices, ips, and node into lists.
dev_list = d.get('net_devices', [])
ips_list = d.get('ips', [])
node_list = d.get('nodes', [])

## scratch space for nodes to operate on
nodes_to_remove = []

## fancy comprehension to get a list of interface names from the system
ifnames = [g[i]['ifname'] for i in range(len(g)) if g[i]['ifname'] != 'lo']

## fancy comprehension to get a list of ips from the system
ip_list_from_sys = [g[i]['addr_info'][0]['local'] for i in range(len(g)) if g[i]['addr_info'][0]['local'] != '127.0.0.1']

## this function gets cpu range values, it uses the function below to parse this output
def get_numa_node_cpu_ranges():
    try:
        lscpu_output = subprocess.check_output(["lscpu"]).decode("utf-8")
        numa_node0_match = re.search(r'NUMA node0 CPU\(s\): (.+)', lscpu_output)
        numa_node1_match = re.search(r'NUMA node1 CPU\(s\): (.+)', lscpu_output)
        if numa_node0_match and numa_node1_match:
            numa_node0_cores = parse_cpu_range(numa_node0_match.group(1))
            numa_node1_cores = parse_cpu_range(numa_node1_match.group(1))
            return {0: set(numa_node0_cores), 1: set(numa_node1_cores)}
        else:
            print("Error: Unable to extract NUMA node core values from lscpu output.")
            return {}
    except Exception as e:
        print(f"Error: {e}")
        return {}


def parse_cpu_range(cpu_range_str):
    # Parse CPU range string like '0-63,128-191' into a list of integers
    cpu_ranges = cpu_range_str.replace(',', ' ').split()
    result = []
    for cpu_range in cpu_ranges:
        start, end = map(int, cpu_range.split('-'))
        result.extend(range(start, end + 1))
    return result

## executes function
numa_node_cpu_ranges = get_numa_node_cpu_ranges()

## paths for file output
output_path_new_unmodified = "/home/opc/balance-cores/output/unmodified_compute0.json"
output_path_new_unmodified = "/home/opc/balance-cores/output/unmodified_drives0.json"
output_path_numa0_drives0 = "/home/opc/balance-cores/output/numa0-drives0.json"
output_path_numa1_drives1 = "/home/opc/balance-cores/output/numa1-drives1.json"
output_path_numa0_compute0 = "/home/opc/balance-cores/output/numa0-compute0.json"
output_path_numa1_compute1 = "/home/opc/balance-cores/output/numa1-compute1.json"

## this is the copy that will be numa1-drives1.json
numa0_drives0 = copy.deepcopy(d)
## this is the copy that will be the numa0-drives0.json
numa1_drives1 = copy.deepcopy(d)
## this is the copy for compute0
numa0_compute0 = copy.deepcopy(d)
## this is the copy for compute1
numa1_compute1 = copy.deepcopy(d)

ips_list_numa1 = numa1_drives1.get('ips', [])
ips_list_numa0 = numa0_drives0.get('ips', [])

numa_node_mapping = {}

for ifname, ip in zip(ifnames, ip_list_from_sys):
	try:
		index = next(i for i, entry in enumerate(g) if entry['ifname'] == ifname)
		numa_node_mapping[ifname] = {
			'numa_node': int(subprocess.check_output(["cat", f"/sys/class/net/{ifname}/device/numa_node"]).decode("utf-8")),
			'ip':ip
		}
	except StopIteration:
		print(f"Error processing{ifname}: Entry not found in 'g' list.")

## work on numa1_drives1 now
print(f"	{numa_node_mapping}")
nodes_to_remove = []
for node, node_info in numa1_drives1['nodes'].items():
	if node == '0':
		continue
	if 'core_id' in node_info:
		core_id = node_info['core_id']
		if core_id not in numa_node_cpu_ranges[1]:
			nodes_to_remove.append(node)

for node in nodes_to_remove:
	del numa1_drives1['nodes'][node]

## add +500 to each rpc_port key's value in numa1_drives1
for node, node_info in numa1_drives1['nodes'].items():
	print(f"{node_info}['rpc_port']")
	node_info['rpc_port'] = node_info['rpc_port'] + 500
	print(f"    {node}, {node_info['rpc_port']}, (changed to add 500)")

## work on numa1_compute1
for node, node_info in numa1_compute1['nodes'].items():
	node_info['rpc_port'] = node_info['rpc_port'] + 500
	print(f"        {node}, rpc port = {node_info['rpc_port']}")

for ifname in ifnames:
    if numa_node_mapping[ifname]['numa_node'] == 0:
        target_ip = numa_node_mapping[ifname]['ip']
        ips_list_numa1.remove(target_ip)

for ifname in ifnames:
	if numa_node_mapping[ifname]['numa_node'] == 0:
		for inet_name, device in enumerate(dev_list):
			if device['name'] == ifname:
				name_to_remove = ifname
				numa1_drives1['net_devices'] = [device for device in numa1_drives1['net_devices'] if device['name'] != name_to_remove]

## work on numa0_drives0
nodes_to_remove = []
for node, node_info in numa0_drives0['nodes'].items():
    if node == '0':
        continue
    if 'core_id' in node_info:
        core_id = node_info['core_id']
        if core_id not in numa_node_cpu_ranges[0]:
            nodes_to_remove.append(node)

for node in nodes_to_remove:
    del numa0_drives0['nodes'][node]

## work on adding 500 to each rpc_port for numa0_drives0
for node, node_info in numa0_compute0['nodes'].items():
	node_info['rpc_port'] = node_info['rpc_port'] + 500
	print(f"        {node}, rpc_ port = {node_info['rpc_port']}")

## work on numa0_compute0
for node, node_info in numa0_compute0['nodes'].items():
	node_info['rpc_port'] = node_info['rpc_port'] + 500
	print(f"	{node}, rpc_port = {node_info['rpc_port']}")

for ifname in ifnames:
    if numa_node_mapping[ifname]['numa_node'] == 1:
        target_ip = numa_node_mapping[ifname]['ip']
        ips_list_numa0.remove(target_ip)

dev_list = numa0_drives0.get('net_devices', [])
for key, value in numa_node_mapping.items():
    if value.get('numa_node') == 1:
        numa0_drives0['net_devices'] = [dev for dev in numa0_drives0['net_devices'] if dev.get('name') != key]

## write out new numa1-drives1.json:
with open(output_path_numa1_drives1, 'w') as numa1_drives1_file:
    json.dump(numa1_drives1, numa1_drives1_file, indent=2)
print(f"Written out to {output_path_numa1_drives1}")

## write out new numa0-drives0.json:
with open(output_path_numa0_drives0, 'w') as numa0_drives0_file:
	json.dump(numa0_drives0, numa0_drives0_file, indent=2)
print(f"Written out to {output_path_numa0_drives0}")

## write out new numa1-compute1.json:
with open(output_path_numa1_compute1, 'w') as numa1_compute1_file:
	json.dump(numa1_compute1, numa1_compute1_file, indent=2)
print(f"Written out to {output_path_numa1_compute1}")

## write out new numa0-compute0.json:
with open(output_path_numa0_compute0, 'w') as numa0_compute0_file:
	json.dump(numa0_compute0, numa0_compute0_file, indent=2)
print(f"Written out to {output_path_numa0_compute0}")

