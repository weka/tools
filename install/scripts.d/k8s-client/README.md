# Kubernetes client scripts

These scripts are executed when wekatester is used with `--workload k8s-client`

These are intended to be run on hosts that will become WEKA clients running
Kubernetes. They focus on hardware, kernel and NIC readiness; the WEKA software
itself is not expected to be present, so no script here requires the weka CLI.

Scripts that need to know the backend addresses (`460_ip_source-based_routing`,
`775_dup_arp_check`) take them from the hosts given on the command line. Without them
the backend-specific parts of those checks are skipped.

Use the `ta` scripts to debug backends after joining a cluster, and the
`client` scripts to prep a conventional (non-Kubernetes) client.

Run this as such:
    `./wekatester -w k8s-client <backend ips/names>`
