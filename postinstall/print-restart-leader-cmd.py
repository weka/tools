#!/usr/bin/env python
import json
import subprocess

def main():
    cfg = json.loads(subprocess.check_output(["weka", "local", "run", "--", "/weka/cfgdump"]))
    leaderNodeId = cfg["leaderId"]
    print("Leader node is: %s" % (leaderNodeId,))
    leaderHostId = cfg["nodes"][leaderNodeId]["hostId"]
    print("Leader host is: %s" % (leaderHostId,))
    ips = cfg["hosts"][leaderHostId]["ips"]
    print("Leader host ips: %s" % (", ".join(ips),))
    print("")
    print("To restart leader, use:")
    print("")
    msg = "ssh %s weka local exec /usr/local/bin/supervisorctl restart weka-management" % (ips[0],)
    print("-"*len(msg))
    print(msg)
    print("-"*len(msg))

if __name__ == '__main__':
    main()
