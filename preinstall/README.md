# Pre-install Tools

Tools useful before Weka installation

## dual-port-routing
Helps to set up routing tables for hosts that have 2 ip interfaces in the same subnet
- CentOS/RHEL only!

## mellanox_fw.sh
 Script to upgrade/install Mellanox MFT tools/driver firmware and set preferred PCI settings for max performance

 Assumptions:
       - OFED installed
       - Internet access for MFT/driver toolsets
       - Run on first cluster host if range is given
       - MFT and MLX variables set at top of script
