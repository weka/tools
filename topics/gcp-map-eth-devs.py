#!/usr/bin/env python3
import os
import requests

headers = {'Metadata-Flavor': 'Google'}
# Make the initial request
initial_response = requests.get('http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/', headers=headers)

## start getting initial response_code
if initial_response.status_code == 200:
    # Extract numbers from the response content
    initial_numbers = [line.strip('/') for line in initial_response.text.split('\n') if line.strip('/')]
    # Iterate through each number in the initial response
    for number in initial_numbers:
        # Construct the target URL using the number
        target_url_mac = f"http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/{number}/mac"  #pull mac from interface number
        target_url_ip = f"http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/{number}/ip" #pull ip from interface number
        target_url_gw = f"http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/{number}/gateway" #pull gw from interface number

        # Make a new request using the constructed URL
        responseMAC = requests.get(target_url_mac, headers=headers)
        responseIP = requests.get(target_url_ip, headers=headers)
        responseGW = requests.get(target_url_gw, headers=headers)

        # Walk /sys for pci address from readlink()
        path = f'/sys/class/net/eth{number}'
        pathOut = os.readlink(path)
        pciAddr = pathOut.split('/')[4]

        # Print response structure
        print(f"Response for eth{number}: --ips {responseIP.text} --gateway {responseGW.text} --netmask = 32 (mapping information PCI Address: {pciAddr} MAC: {responseMAC.text})")
else:
    print(f"non 200 response code!")
