#!/usr/bin/env python3

import json
import subprocess
import sys
import argparse


def main():
    weka_container = []
    containers = json.loads(subprocess.check_output(["weka", "local", "ps", "-J"]))
    for wc in containers:
        if wc["type"] == "weka" and wc["internalStatus"]["state"] == "READY":
            weka_container += [wc["name"]]
    if not weka_container:
        print("No ready weka container found")
        sys.exit(1)
    for name in weka_container:
        try:
            cfg = json.loads(
                subprocess.check_output(["sudo", "weka", "local", "run", "-C", name, "--", "/weka/cfgdump"]))
            if not cfg:
                continue
            else:
                break
        except Exception as e:
            print("Unable able to determine weka container %s" % (e,))

    leaderNodeId = cfg["leaderId"]
    print("Leader node is: %s" % (leaderNodeId,))
    leaderHostId = cfg["nodes"][leaderNodeId]["hostId"]
    print("Leader host is: %s" % (leaderHostId,))
    try:
        ips = cfg["hosts"][leaderHostId]["ips"]
    except KeyError:
        ips = cfg["hosts"][leaderHostId]["_ips"]
    print("Leader host ips: %s" % (", ".join(ips),))
    container_name = cfg["hosts"][leaderHostId]["containerName"]
    print("Leader container name is: %s" % (container_name,))

    parser = argparse.ArgumentParser(description="Leader Restart")

    parser.add_argument(
        "-f",
        "--force",
        dest="force_restart",
        action="store_true",
        default=False,
        help="To force leader restart",
    )

    args = parser.parse_args()

    if args.force_restart:
        cmd = ["ssh", ips[0], "weka", "local", "exec", "-C", container_name, "/usr/local/bin/supervisorctl", "restart", "weka-management"]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            print("SSH command failed. Unable to restart leader.")
    else:
        print("")
        print("To restart leader, use:")
        print("")
        msg = "ssh %s weka local exec -C %s /usr/local/bin/supervisorctl restart weka-management" % (ips[0], container_name)
        print("-" * len(msg))
        print(msg)
        print("-" * len(msg))

if __name__ == '__main__':
    main()
