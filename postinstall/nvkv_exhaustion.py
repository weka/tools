"""
Check and try to handle NVKV exhaustion
"""

import argparse
import json
import logging
import subprocess
import time
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger()

WRITABLE = "Writable"
UNWRITABLE = "Unwritable"

def main():
    args = parse_args()
    app = App(args)
    app.main()

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stall-file', type=Path, default="", help="Created on critical errors. While it exists this script is disabled. Ignored if empty. (default: none)")
    parser.add_argument('--log-file', default='nvkv_exhaustion.log', help="Path of the debug log file (default: nvkv_exhaustion.log)")
    parser.add_argument('--critical-log-file', default='nvkv_exhaustion_critical.log', help="Path of the critical log file (for pager duty) (default: nvkv_exhaustion_critical.log)")
    parser.add_argument('--log-level', default=logging.DEBUG, help="Log debug level (default: DEBUG)")
    parser.add_argument('--loop', action='store_true', help="Check in a loop forever")
    parser.add_argument('--loop-delay', type=int, default=10, help="Seconds to sleep between loops (default: 10)")
    parser.add_argument('--threshold', type=int, default=90, help="NVNK used percent above which we should set Unwritable and restart (default: 90)")
    parser.add_argument('--poll-interval', type=float, default=1, help="Seconds to sleep between status polls (e.g. between disk_writable_state calls)")
    parser.add_argument('--delay-before-restart', type=float, default=20, help="Seconds to sleep before restarting drive node (default: 20)")
    parser.add_argument('--delay-after-restart', type=float, default=20, help="Seconds to sleep after restarting drive node (default: 20)")
    parser.add_argument('--timeout', type=int, default=300, help="Max seconds to wait for disk writable state to change to the expected state (default: 300)")
    parser.add_argument('--max-unwritable', type=int, default=20, help="Max amount of unwritable disk allowed. If more disks are unwritable, the script would doesn't proceed. (default: 20)")
    parser.add_argument('--allowed-failures', type=int, default=0, help="Max amount of failures allowed before restarting drive nodes. (default: 0)")
    args = parser.parse_args()
    if not args.stall_file.name:
        args.stall_file = None
    return args

class App:
    def __init__(self, args):
        self.args = args
        self.set_logging()

    def set_logging(self):
        log_handlers = [logging.StreamHandler()]

        if self.args.log_file:
            log_handlers.append(logging.FileHandler(self.args.log_file))

        if self.args.critical_log_file:
            criticalHandler = logging.FileHandler(self.args.critical_log_file)
            criticalHandler.setLevel(logging.CRITICAL)
            log_handlers.append(criticalHandler)

        logging.basicConfig(
            level=self.args.log_level,
            format="%(asctime)s [%(levelname)-8s] %(message)s",
            handlers=log_handlers
        )

    def main(self):
        if self.args.stall_file:
            if self.args.stall_file.exists():
                logger.error("- NVKV exhaustion check script is STALLED by previous critical error! Remove stall file %s to unstall. -", self.args.stall_file.absolute())
                exit(1)

        if self.args.max_unwritable == 0:
            self.critical_error("Cannot run with max_unwritable == 0")

        logger.info("--- Start NVKV exhaustion check script ---")

        try:
            while True:
                logger.info("-- Start check --")
                self.check_once()
                logger.info("-- End check --")
                if not self.args.loop:
                    break
                logger.info("Sleep before next check (%s)...", self.args.loop_delay)
                time.sleep(self.args.loop_delay)
        except Exception as e:
            logger.exception("Unexpected exception")
            self.critical_error("Unexpected exception %s: %s", type(e).__name__, e)

        logger.info("--- End NVKV exhaustion check script ---")

    def check_once(self):
        drives = self.get_drives()

        drives.sort(key=lambda x: (x.writable == WRITABLE, x.used_nvkv_space_percent), reverse=True)
        num_unwritable = sum(1 for drive in drives if drive.writable != WRITABLE)
        # NOTE: if we have UNWRITABLE drives that are above threshold,
        # that's very bad. But we'll reach those as soon as we run out
        # of above-threshold drives to set-unwritable, and start
        # resetting unwritable drives

        logger.info("Top 20 drives with highest NVKV usage (unwritables=%s):", num_unwritable)
        self.log_drives(drives[:20])

        if self.set_unwritable_if_applicable(drives, num_unwritable):
            return

        if self.reset_unwritable_drive(drives):
            return

    def reset_unwritable_drive(self, drives):
        nodes_to_drives = defaultdict(list)
        for drive in drives:
            nodes_to_drives[drive.node_id].append(drive)

        for drive in drives:
            if drive.writable != WRITABLE:
                self.reset_unwritable_drive_owner_node(drive, nodes_to_drives)
                return True

    def set_unwritable_if_applicable(self, drives, num_unwritable):
        fullest_drive = drives[0]
        assert fullest_drive.writable == WRITABLE
        if fullest_drive.used_nvkv_space_percent < self.args.threshold:
            logger.info("Disk %s has the highest NVKV usage of %s%%, which is below the threshold %s%%. Nothing to do.", fullest_drive.disk_id, fullest_drive.used_nvkv_space_percent, self.args.threshold)
            return
        if num_unwritable < self.args.max_unwritable:
            logger.info("NVKV usage of %s on %s is %s%% (%s), higher than threshold %s%%. Will try to fix it.",
                        fullest_drive.writable, fullest_drive.disk_id, fullest_drive.node_id, fullest_drive.used_nvkv_space_percent,
                        self.args.threshold)
            self.set_unwritable(fullest_drive, wait_for_state=True)
            return True
        # We have over-threshold WRITABLE drive, but we have too many unwritable drives:
        num_failures = self.get_num_failures()
        if num_failures > self.args.allowed_failures:
            self.critical_error("NVKV usage of %s on %s is %s%%, higher than threshold %s%%. We have too many unwritables (%s >= %s), and %s failures (> %s) so can't restart drive nodes",
                                fullest_drive.disk_id, fullest_drive.node_id, fullest_drive.used_nvkv_space_percent, self.args.threshold,
                                num_unwritable, self.args.max_unwritable, num_failures, self.args.allowed_failures)
        logger.info("NVKV usage of %s on %s is %s%%, higher than threshold %s%%, but too many unwritables, will reset unwritable disks first.",
                    fullest_drive.disk_id, fullest_drive.node_id, fullest_drive.used_nvkv_space_percent, self.args.threshold)

    def reset_unwritable_drive_owner_node(self, unwritable_drive, nodes_to_drives):
        if self.get_num_failures() > self.args.allowed_failures:
            return

        node_id = unwritable_drive.node_id
        node_drives = nodes_to_drives[node_id]
        logger.info("%s is unwritable, will reset %s. First setting drives in it as Unwritable", unwritable_drive.disk_id, node_id)
        for drive in node_drives:
            if drive.writable != UNWRITABLE:
                self.set_unwritable(drive, wait_for_state=False)

        logger.info("Waiting for drives on %s to be Unwritable", node_id)
        for drive in node_drives:
            self.wait_for_drive_writable_state(drive, UNWRITABLE)

        node_drives = self.refresh_drive_list(node_drives)
        self.log_drives(node_drives)

        logger.info("Delaying %s before considering restart of drive node", self.args.delay_before_restart)
        time.sleep(self.args.delay_before_restart)

        if self.get_num_failures() > self.args.allowed_failures:
            return

        self.restart_node(node_id)

        logger.info("Waiting for drives on %s to be Writable", node_id)
        for drive in node_drives:
            self.wait_for_drive_writable_state(drive, WRITABLE)

        logger.info("Drives on %s after becoming Writable", node_id)
        node_drives = self.refresh_drive_list(node_drives)
        self.log_drives(node_drives)

        logger.info("Delaying %s after restart of drive node", self.args.delay_after_restart)
        time.sleep(self.args.delay_after_restart)

        node_drives = self.refresh_drive_list(node_drives)
        self.log_drives(node_drives)

        for restarted_drive in node_drives:
            if restarted_drive.used_nvkv_space_percent >= self.args.threshold:
                self.critical_error("Restarted drive %s STILL at NVKV utilization %s after restart of %s!",
                                    restarted_drive.disk_id, restarted_drive.used_nvkv_space_percent, node_id)

    def find_drive(self, drives, disk_id):
        for drive in drives:
            if drive.disk_id == disk_id:
                return drive
        return None

    def get_drives(self, disk_ids=[], show_removed=False):
        cmd = ['weka', 'cluster', 'drive', '-J'] + [strip_id(disk_id) for disk_id in disk_ids]
        if show_removed:
            cmd.append('--show-removed')
        output = subprocess.check_output(cmd)
        return Bunch.from_json(output)

    def set_unwritable(self, drive, *, wait_for_state):
        logger.info("Setting %s on %s as unwritable", drive.disk_id, drive.node_id)
        subprocess.check_output(['weka', 'debug', 'jrpc', 'disk_set_unwritable', f'diskId={drive.disk_id}', 'force=true'])
        if wait_for_state:
            self.wait_for_drive_writable_state(drive, UNWRITABLE)

    def wait_for_drive_writable_state(self, drive, expected_state):
        assert expected_state in (WRITABLE, UNWRITABLE)
        logger.info("Waiting for %s on %s to be %s", drive.disk_id, drive.node_id, expected_state)
        timeout = self.timeout()
        while True:
            drive, = self.refresh_drive_list([drive])
            logger.info("Drive %s on %s is %s/%s (NVKV %s%%) (waiting for %s/ACTIVE)",
                        drive.disk_id, drive.node_id, drive.writable, drive.status, drive.used_nvkv_space_percent, expected_state)
            if drive.status == "ACTIVE" and drive.writable == expected_state:
                return
            if timeout.expired():
                self.critical_error("Timed out waiting for drive %s on %s to become %s, it is still %s", drive.disk_id, drive.node_id, expected_state, drive.writable)
            time.sleep(self.args.poll_interval)

    def log_drives(self, drives):
        for drive in drives:
            self.log_drive(drive)
        return drives

    def refresh_drive_list(self, drives):
        old_disk_ids = {drive.disk_id for drive in drives}
        drives_new = self.get_drives(old_disk_ids, show_removed=True) # Show removed just in case some of the drives were removed in between...
        new_disk_ids = {drive.disk_id for drive in drives_new}
        if new_disk_ids != old_disk_ids:
            self.critical_error("New drive listing is different: %s != %s", sorted(new_disk_ids), sorted(old_disk_ids))
        return drives_new

    def log_drive(self, drive):
        logger.info("Drive %-12s on %-12s %-12s uses %s%% of NVKV (status: %s, writable: %s)", drive.disk_id, drive.node_id, drive.host_id, drive.used_nvkv_space_percent, drive.status, drive.writable)

    def get_num_failures(self):
        status = self.get_rebuild_status()
        if status.unavailableMiB > 0:
            logger.info("%s unavailable MiB exist", status.unavailableMiB)
            return 5
        state = status.protectionState

        state.sort(key=lambda x: x.numFailures)
        assert [x.numFailures for x in state] == list(range(len(state))), f'Unexpected protection state: {state}'

        for protection in state[::-1]:
            if protection.MiB != 0:
                protections = len(state) - protection.numFailures - 1
                logger.info("%s MiB is in %s numFailures (%s protections)", protection.MiB, protection.numFailures, protections)
                return protection.numFailures
        assert False, "No protection level has any data"

    def get_rebuild_status(self):
        return Bunch.from_json(subprocess.check_output(['weka', 'status', 'rebuild', '-J']))

    def restart_node(self, node_id):
        logger.info("Restart node %s", node_id)
        return json.loads(subprocess.check_output(['weka', 'debug', 'manhole', '--node', strip_id(node_id), 'request_restart', '-J']))

    def critical_error(self, format_message, *args):
        logger.critical(format_message, *args)
        if self.args.stall_file:
            self.args.stall_file.touch()
        subprocess.check_output(['weka', 'events', 'trigger-event', ('%s (NVKVcheck)' % (format_message % args))[:128]])
        exit(1)

    def timeout(self):
        return Timeout(self.args.timeout)

####

class Timeout:
    def __init__(self, seconds):
        self.expiration = time.time() + seconds

    def expired(self):
        return time.time() >= self.expiration

def strip_id(raw_id):
    start = raw_id.index("<") + 1;
    end = raw_id.index(">")
    return raw_id[start:end]

####

# Copied from easypy:
class Bunch(dict):

    __slots__ = ("__stop_recursing__",)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            if name[0] == "_" and name[1:].isdigit():
                return self[name[1:]]
            raise AttributeError("%s has no attribute %r" % (self.__class__, name))

    def __getitem__(self, key):
        try:
            return super(Bunch, self).__getitem__(key)
        except KeyError:
            from numbers import Integral
            if isinstance(key, Integral):
                return self[str(key)]
            raise

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError:
            raise AttributeError("%s has no attribute %r" % (self.__class__, name))

    def __getstate__(self):
        return self

    def __setstate__(self, dict):
        self.update(dict)

    def __repr__(self):
        if getattr(self, "__stop_recursing__", False):
            items = sorted("%s" % k for k in self if isinstance(k, str) and not k.startswith("__"))
            attrs = ", ".join(items)
        else:
            dict.__setattr__(self, "__stop_recursing__", True)
            try:
                items = sorted("%s=%r" % (k, v) for k, v in self.items()
                               if isinstance(k, str) and not k.startswith("__"))
                attrs = ", ".join(items)
            finally:
                dict.__delattr__(self, "__stop_recursing__")
        return "%s(%s)" % (self.__class__.__name__, attrs)

    def _repr_pretty_(self, *args, **kwargs):
        from easypy.humanize import ipython_mapping_repr
        return ipython_mapping_repr(self, *args, **kwargs)

    def to_dict(self):
        return unbunchify(self)

    def to_json(self):
        import json
        return json.dumps(self.to_dict())

    def to_yaml(self):
        import yaml
        return yaml.dump(self.to_dict())

    def copy(self, deep=False):
        if deep:
            return _convert(self, self.__class__)
        else:
            return self.__class__(self)

    @classmethod
    def from_dict(cls, d):
        return _convert(d, cls)

    @classmethod
    def from_json(cls, d):
        import json
        return cls.from_dict(json.loads(d))

    @classmethod
    def from_yaml(cls, d):
        import yaml
        return cls.from_dict(yaml.load(d))

    @classmethod
    def from_xml(cls, d):
        import xmltodict
        return cls.from_dict(xmltodict.parse(d))

    def __dir__(self):
        members = set(k for k in self if isinstance(k, str) and (k[0] == "_" or k.replace("_", "").isalnum()))
        members.update(dict.__dir__(self))
        return sorted(members)

    def without(self, *keys):
        "Return a shallow copy of the bunch without the specified keys"
        return Bunch((k, v) for k, v in self.items() if k not in keys)

    def but_with(self, **kw):
        "Return a shallow copy of the bunch with the specified keys"
        return Bunch(self, **kw)


def _convert(d, typ):
    if isinstance(d, dict):
        return typ(dict((str(k), _convert(v, typ)) for k, v in d.items()))
    elif isinstance(d, (tuple, list, set)):
        return type(d)(_convert(e, typ) for e in  d)
    else:
        return d


def unbunchify(d):
    """Recursively convert Bunches in `d` to a regular dicts."""
    return _convert(d, dict)


def bunchify(d=None, **kw):
    """Recursively convert dicts in `d` to Bunches.
    If `kw` given, recursively convert dicts in it to Bunches and update `d` with it.
    If `d` is None, an empty Bunch is made."""
    d = _convert(d, Bunch) if d is not None else Bunch()
    if kw:
        d.update(bunchify(kw))
    return d

####

if __name__ == '__main__':
    main()
