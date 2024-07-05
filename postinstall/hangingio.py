#!/usr/bin/env python3

import json
import re
import argparse
import subprocess
import sys
import logging

def parse_args():
    parser = argparse.ArgumentParser(description='Filter HangingIos by age.')
    parser.add_argument('--age', type=int, default=24, help='The minimum age in hours to filter HangingIos entries.')
    parser.add_argument('--log-file', type=str, default='hangingios.log', help='The log file to save the process logs.')
    return parser.parse_args()

def setup_logging(log_file):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def get_hangingios_alerts():
    try:
        output = subprocess.check_output(["weka", "alerts", "--filter", "type=HangingIos", "--no-header", "-J"])
        alerts = json.loads(output)
        return [alert for alert in alerts if "DriverFrontend" in alert.get('description', '')]
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to fetch alerts: {e}")
        sys.exit(1)

def parse_hangingios_description(description):
    pattern = re.compile(
        r'HangingIos\(NodeId<\d+>, (?:(\d+) days?, )?(?:(\d+) hours?, )?(?:(\d+) minutes?, )?(?:(\d+) secs?, and )?(?:\d+ ms, )?fid=0x[a-fA-F0-9]+, entry=\d+, operation=[^,]+, state=[^,]+, SnapViewId<(\d+)>, Pid<\d+>, InodeId<(\d+)>\)'
    )
    return pattern.findall(description)

def duration_to_hours(days, hours, minutes, seconds):
    return (int(days) if days else 0) * 24 + \
           (int(hours) if hours else 0) + \
           (int(minutes) if minutes else 0) / 60 + \
           (int(seconds) if seconds else 0) / 3600

def filter_and_collect_entries(matches, min_age):
    unique_inodes = set()
    results = []
    for days, hours, minutes, seconds, snap_id, inode_id in matches:
        if duration_to_hours(days, hours, minutes, seconds) > min_age:
            if inode_id not in unique_inodes:
                unique_inodes.add(inode_id)
                results.append({"SnapViewId": snap_id, "InodeId": inode_id})
    return results

def process_entries(entries):
    for result in entries:
        logging.info(f"Working on {result}")
        try:
            subprocess.check_output(
                ["weka", "debug", "fs", "drop-dirty-cache", result['InodeId'], "--snap-view-id", result['SnapViewId']],
                stderr=subprocess.STDOUT
            )
            logging.info(f"Successfully processed {result}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to process {result}: {e}")

def main():
    args = parse_args()
    setup_logging(args.log_file)

    weka_alerts = get_hangingios_alerts()

    if not weka_alerts:
        logging.info("No DriverFrontend hangingio alerts found")
        sys.exit()

    all_filtered_entries = []
    for alert in weka_alerts:
        matches = parse_hangingios_description(alert['description'])
        filtered_entries = filter_and_collect_entries(matches, args.age)
        all_filtered_entries.extend(filtered_entries)

    if all_filtered_entries:
        logging.info(f"Found {len(all_filtered_entries)} DriverFrontend hanging I/O entries exceeding {args.age} hours.")
        process_entries(all_filtered_entries)
    else:
        logging.info(f"No DriverFrontend hanging I/O entries found exceeding {args.age} hours.")

if __name__ == "__main__":
    main()
