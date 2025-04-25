
DESCRIPTION="Check boot mounts"
SCRIPT_TYPE="parallel-compare-backends"

lsblk -fs --json | /usr/bin/env python3 -c '
import sys
import json


try:
    input_data = sys.stdin.read()
    data = json.loads(input_data)
except json.JSONDecodeError as e:
    print("Invalid JSON input:", e)
except Exception as e:
    print("Error:", e)

if "blockdevices" in data:
    for device_dict in data["blockdevices"]:
        if "children" in device_dict and device_dict["mountpoint"] is not None:
            print(device_dict["children"][0]["name"])
else:
    print("error: no blockdevices in input")
' | sort | uniq

exit 0