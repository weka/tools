# onprem-installtools
Tools to help manually install clusters

wekareset.sh - reset the cluster nodes to STEM mode.   Use this in lieu of wekawhacker.sh.   If it does not succeed, try wekawhacker.sh for a rude uninstall. (smile)

wekadeploy.sh - deploy weka to a cluster - takes two arguments: the weka tar filename, and a file containing a list of hosts, one per line.  Copies tar file to hosts, unpacks, and installs.

wekawhacker.sh - removes weka from a failed installation attempt.  Takes one argument: a file containing a list of hosts, one per line.

wekaautoconfig - automatically configures a cluster from a list of hostnames/ips with minimal user input.  NOTE: this REQURES that the hosts all be identical (homegeneous cluster), include the same number and type of drives, network interfaces, cpu, ram, etc.).  HA Configurations are automatically detected and configured.
