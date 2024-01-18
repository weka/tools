#!/usr/bin/env python3
import json

with open ('/home/opc/balance-cores/original/drives0.json') as f:
	d = json.load(f)

with open ('/home/opc/balance-cores/output/numa0-drives0.json') as g:
	numa0_drives0 = json.load(g)

with open ('/home/opc/balance-cores/output/numa1-drives1.json') as h:
	numa1_drives1 = json.load(h)

with open ('/home/opc/balance-cores/original/compute0.json') as j:
	k = json.load(j)

with open ('/home/opc/balance-cores/output/numa0-compute0.json') as l:
	numa0_compute0 = json.load(l)

with open ('/home/opc/balance-cores/output/numa1-compute1.json') as n:
	numa1_compute1 = json.load(n)

## drives0.json, net_devs, ip and node
drives0_dev_list = d.get('net_devices', [])
drives0_ips_list = d.get('ips', [])
drives0_node_core_ids = d.get('nodes', [])

## numa0 net_devs, ip, node core_ids
numa0_dev_list = numa0_drives0.get('net_devices', [])
numa0_ips_list = numa0_drives0.get('ips', [])
numa0_node_core_ids = numa0_drives0.get('nodes', [])

## numa0 net_devs, ip, node core_ids
numa1_dev_list = numa1_drives1.get('net_devices', [])
numa1_ips_list = numa1_drives1.get('ips', [])
numa1_node_core_ids = numa1_drives1.get('nodes', [])

for i in drives0_dev_list:
	print(f"drives0.json list is {i['name']}")

for i in drives0_ips_list:
	print(f"drives0 ips list is {i}")

for node, node_info in d['nodes'].items():
	core_id = node_info['core_id']
	node_rpc_port = node_info['rpc_port']
	print(f"  drives0.json is assigned this node and core_ids: Node id {node} is {core_id} and rpc port is {node_rpc_port}")

for i in numa0_dev_list:
	print(f"numa0 dev list is {i['name']}")

for i in numa0_ips_list:
	print(f"numa0 ips list is {i}")

for node, node_info in numa0_drives0['nodes'].items():
    core_id = node_info['core_id']
    node_rpc_port = node_info['rpc_port']
    print(f"	numa0_drives0 is assigned this node and core_ids: Node id {node} is {core_id} and rpc port is {node_rpc_port}")

for i in numa1_dev_list:
	print(f"numa1 dev list is {i['name']}")

for i in numa1_ips_list:
	print(f"numa1 ips list is {i}")

for node, node_info in numa1_drives1['nodes'].items():
    core_id = node_info['core_id']
    node_rpc_port = node_info['rpc_port']
    print(f"	numa1_drives1 is assigned this node and core_ids: Node id {node} is {core_id} and rpc port is {node_rpc_port}")

for node, node_info in k['nodes'].items():
	core_id = node_info['core_id']
	node_rpc_port = node_info['rpc_port']
	print(f"    compute.json is assigned this node and core_ids: Node id {node} is {core_id} and rpc port is {node_rpc_port}")

for node, node_info in numa0_compute0['nodes'].items():
	core_id = node_info['core_id']
	node_rpc_port = node_info['rpc_port']
	print(f"numa0_compute0 is assigned this node and core_ids: Node id {node} is {core_id} and rpc port is {node_rpc_port}")

for node, node_info in numa1_compute1['nodes'].items():
	core_id = node_info['core_id']
	node_rpc_port = node_info['rpc_port']
	print(f"numa1_compute1 is assigned this node and core_ids: Node id {node} is {core_id} and rpc port is {node_rpc_port}")

