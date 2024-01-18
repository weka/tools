#!/usr/bin/env python3
import sys
##
## take values like this:
## all   network   2024-01-16T20:17:00  PORT_TX_BYTES[networkPortId: UDP_PORT_2]   0 Bytes/Sec
## all   network   2024-01-16T20:17:00  PORT_RX_BYTES[networkPortId: UDP_PORT_0]   6.82867e+06 Bytes/Sec
## all   network   2024-01-16T20:17:00  PORT_RX_BYTES[networkPortId: DPDK_PORT_0]  7.29535e+07 Bytes/Sec
## all   network   2024-01-16T20:17:00  PORT_RX_BYTES[networkPortId: RDMA_PORT_0]  0 Bytes/Sec
## and print out GB/s values.
##
##

# Check if a command line argument is provided
if len(sys.argv) != 3:
    print("Usage: python script_name.py <value_in_bytes_per_sec>")
    sys.exit(1)

# Get the input from the command line argument
input_str = sys.argv[1]
#input_str = input("Enter the value in Bytes/Sec: ")
bytes_per_sec_str = input_str.split(' ')[0]
bytes_per_sec = float(bytes_per_sec_str)
bytes_per_gb = 2**30 ## conversion factor to GB
bytes_per_mb = 2**20 ## conversion factor to MB
print(f"Given value in Bytes/Sec: {bytes_per_sec} Bytes/Sec")
print(f"Conversion factor: 1 GB = {bytes_per_gb} Bytes")
gb_per_sec = bytes_per_sec / bytes_per_gb
mb_per_sec = bytes_per_sec / bytes_per_mb
print(f"{bytes_per_sec} Bytes/Sec is approximately {gb_per_sec:.5f} GB/s")
print(f"{bytes_per_sec} Bytes/Sec is approximately {mb_per_sec:.5f} MB/s")
