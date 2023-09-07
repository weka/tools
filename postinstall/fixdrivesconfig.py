#!/usr/bin/env python3
import json
import subprocess
import sys

def parse_disk_id(disk_id):
    assert disk_id.startswith("DiskId<")
    assert disk_id.endswith(">")
    return int(disk_id[7:-1])

def main():
    weka_drives = json.loads(subprocess.check_output(["weka", "debug", "config", "show", "disks"]))
    fake_drives = []
    for disk_id, drive in weka_drives.items():
        target_state = drive['_targetState']['state']
        committed_state = drive['_committedState']['state']
        lastPhaseoutGeneration = drive['lastPhaseOutGeneration']
        lastPhaseOutSizeB = drive['lastPhaseOutSizeB']
        sizeB = drive['sizeB']
        if target_state == "INACTIVE" and lastPhaseoutGeneration == "ConfigGeneration<1>" and lastPhaseOutSizeB != sizeB:
            fake_drives.append(dict(disk_id=disk_id, committed_state=committed_state, target_state=target_state, lastPhaseOutSizeB=lastPhaseOutSizeB, sizeB=sizeB))
    if not fake_drives:
        print("No drives to fix configuration for...", file=sys.stderr)
        return
    print("Generating commands to fix configuration of all drives with lastPhaseoutGeneration == ConfigGeneration<1>:", file=sys.stderr)
    print(f"  {', '.join(drive['disk_id'] for drive in fake_drives)}", file=sys.stderr)
    print()
    print(f"Make sure to back up the configuration json file before running the following commands", file=sys.stderr)
    print(f"To backup weka config use sudo weka local run --container drives0 /weka/cfgdump > weka_config", file=sys.stderr)
    for drive in fake_drives:
        disk_id = parse_disk_id(drive["disk_id"])
        print(f"weka debug config override disks[{disk_id}].lastPhaseOutSizeB {drive['sizeB']}")


if __name__ == '__main__':
    main()
