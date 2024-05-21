#!/usr/bin/env python3
import os
import io
import time
import socket
import subprocess
import select
import re
from pprint import pformat
import logging


class LoggerCustomFormatter(logging.Formatter):
    cyan = "\x1b[36;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_info = "[%(asctime)s][%(name)s][%(levelname)s][%(filename)s:%(lineno)d]"
    format_msg = " %(message)s"

    FORMATS = {
        logging.DEBUG: green + format_info + reset + format_msg,
        logging.INFO: cyan + format_info + reset + format_msg,
        logging.WARNING: yellow + format_info + reset + format_msg,
        logging.ERROR: red + format_info + reset + format_msg,
        logging.CRITICAL: bold_red + format_info + reset + format_msg
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

logger = logging.getLogger("PCIWatchDog")
logger.setLevel(logging.DEBUG)
logger_fmt = LoggerCustomFormatter()

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logger_fmt)
logger.addHandler(console_handler)


LOGGER_DIR = '/opt/weka/logs'
if not os.path.exists(LOGGER_DIR) or not os.path.isdir(LOGGER_DIR):
    LOGGER_DIR = '/tmp'

file_handler = logging.FileHandler(os.path.join(LOGGER_DIR, 'pci_watchdog.log'))
file_handler.setFormatter(logger_fmt)
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)


def get_uptime():
    with open('/proc/uptime', 'r') as f:
        return float(f.readline().split()[0])


def test_nvme_fmt():
    res = PCIWatchDog.RE_NVME_FAILURE_FMT.match("nvme nvme19: Removing after probe status: -12")
    assert res == None, pformat(res)

    res = PCIWatchDog.RE_NVME_FAILURE_FMT.match("nvme nvme19: Removing after probe failure status: -12")
    assert len(res.groups()) == 2 and res.groups()[0] == "nvme19" and res.groups()[1] == "-12", pformat(res)
    logger.debug(res.groups())

    res = PCIWatchDog.RE_NVME_FAILURE_FMT.match("nvme nvme2n1: Removing after probe failure status: -12")
    assert len(res.groups()) == 2 and res.groups()[0] == "nvme2n1" and res.groups()[1] == "-12", pformat(res)
    logger.debug(res.groups())

    res = PCIWatchDog.RE_NVME_FAILURE_FMT.match("nvme nvme0: Removing after probe failure status: -19")
    assert len(res.groups()) == 2 and res.groups()[0] == "nvme0" and res.groups()[1] == "-19", pformat(res)
    logger.debug(res.groups())


class PCIWatchDog:
    # nvme nvme19: Removing after probe failure status: -12
    # nvme nvme0: Removing after probe failure status: -19
    RE_NVME_FAILURE_FMT = re.compile('^nvme (.+): Removing after probe failure status: (-\d+)$')
    # nvme nvme0: pci function 0000:87:00.0
    RE_NVME_DEV_TO_ADDR_FMT = re.compile('^nvme (.+): pci function (.+)$')

    def __init__(self, file_handler, ignore_timestamp=False, dry_run=False):
        self._hostname = socket.gethostname()
        self._file_handler = file_handler
        self._dry_run = dry_run
        self._started_at_uptime = 0 if ignore_timestamp else get_uptime()
        self._simulated_mode = True if isinstance(self._file_handler, io.StringIO) else False

        # self._all_pcis = {}
        # self._nvme_pcis = {}
        self._failed_nvme_list = []
        self._weka_events_list = []
        self._nvme_to_pci_addr = {}
        self._nvme_remove_time = {}
        self._nvme_rescan_time = {}


    def _verify_weka_sent_events(self):
        try:
            while len(self._weka_events_list) > 0:
                proc = self._weka_events_list[0]
                if proc.poll() is None:
                    return
                if proc.returncode != 0:
                    self._weka_events_list[0] = subprocess.Popen(proc.args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return

                logger.info("weka event sent : %s", proc.args)
                self._weka_events_list.pop(0)

        except Exception as e:
            logger.exception("failed verify weka sent events")


    def _weka_event(self, msg):
        msg = f"PCIWatchDog|{self._hostname} {msg}"
        logger.info("weka event: %s", msg)
        if len(msg) > 128:
            logger.error("weka event max length is 128 will be trimmed")
            msg = msg[0:128]

        self._weka_events_list.append(subprocess.Popen(["weka", "events", "trigger-event", msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))


    def _weka_event_nvme_failure_identified(self, nvme, pci_addr, msg):
        self._weka_event(f"nvme({nvme}) pci_addr({pci_addr}) {msg}")


    def _weka_event_nvme_recovered(self, nvme, pci_addr):
        self._weka_event(f"nvme({nvme}) pci_addr({pci_addr}) recovered")


    # def pcis(self):
    #     if self._all_pcis:
    #         return self._all_pcis

    #     lines = subprocess.check_output(["lspci", "-D"]).decode("utf-8").splitlines()
    #     self._all_pcis = { line.split(" ")[0]: " ".join(line.split(" ")[1:]) for line in lines }
    #     logger.debug("all pcis : %s", pformat(self._all_pcis))
    #     return self._all_pcis


    # def nvme_pcis(self):
    #     if self._nvme_pcis:
    #         return self._nvme_pcis

    #     self._nvme_pcis = {k: v for k, v in self.pcis().items() if v.startswith("Non-Volatile memory controller") }
    #     logger.debug("NVMe pcis : %s", self._nvme_pcis)
    #     return self._nvme_pcis


    def _kmsg_nvme_failure(self, kmsg_time, kmsg_msg):
        res = self.RE_NVME_FAILURE_FMT.match(kmsg_msg)
        if res is None or len(res.groups()) != 2:
            return False

        nvme=res.groups()[0].strip(' \n\t')
        error_code=res.groups()[1].strip(' \n\t')
        self._failed_nvme_list.append(nvme)
        pci_addr = self._nvme_to_pci_addr.get(nvme, "")
        logger.warning("nvme(%s) pci_addr(%s) failed with error code %s", nvme, pci_addr, error_code)
        self._weka_event_nvme_failure_identified(nvme, pci_addr, f"time({int(kmsg_time)*1000000}) {kmsg_msg}")
        return True


    def _kmsg_nvme_addr(self, kmsg_time, kmsg_msg):
        res = self.RE_NVME_DEV_TO_ADDR_FMT.match(kmsg_msg)
        if res is None or len(res.groups()) != 2:
            return False

        nvme_name=res.groups()[0].strip(' \n\t')
        nvme_pci_addr=res.groups()[1].strip(' \n\t')
        logger.info("nvme(%s) pci_addr(%s) pci function", nvme_name, nvme_pci_addr)
        prev_pci_addr = self._nvme_to_pci_addr.get(nvme_name)
        if prev_pci_addr is not None and prev_pci_addr != nvme_pci_addr:
            logger.error("we seen nvme(%s) before with pci_addr(%s), now pci_addr(%s). will update to the latest.", nvme_name, prev_pci_addr, nvme_pci_addr)
        self._nvme_to_pci_addr[nvme_name] = nvme_pci_addr
        return True


    def poll(self):
        did_something = 0
        while True:
            if isinstance(self._file_handler, io.TextIOWrapper):
                r, _, _ = select.select([ self._file_handler ], [], [], 0)
                if self._file_handler not in r:
                    break
            elif self._simulated_mode and self._file_handler.closed:
                break

            line = self._file_handler.readline()
            if not line or len(line) == 0:
                if self._simulated_mode:
                    self._file_handler.close()
                break

            did_something = 1
            line = line.strip(' \n\t')
            # logger.debug(line)
            line_split = line.split(";")

            if len(line_split) < 2:
                continue

            pri, index, time_from_boot, _ = line_split[0].split(",")
            time_from_boot = float(time_from_boot) / 1000000
            if time_from_boot < self._started_at_uptime:
                # logger.debug("skipping. happend before our time")
                continue

            logger.debug(line)
            kmsg_msg = ";".join(line_split[1:]).strip(' \n\t')
            if self._kmsg_nvme_failure(time_from_boot, kmsg_msg):
                continue
            if self._kmsg_nvme_addr(time_from_boot, kmsg_msg):
                continue

        return did_something


    def _nvme_remove(self, nvme, pci_addr):

        def _pci_rm(nvme, pci_addr):
            logger.info("nvme(%s) pci_addr(%s) pci remove", nvme, pci_addr)
            if not self._dry_run:
                _path = os.path.join("/sys/bus/pci/devices", pci_addr, "remove")
                if os.path.exists(_path):
                    with open(_path, "w") as f:
                        f.write("1")
                else:
                    # already removed ?
                    logger.warning("nvme(%s) pci_addr(%s) path not exist: %s", nvme, pci_addr, _path)

        if self._simulated_mode:
            _pci_rm(nvme, pci_addr)
            return 1

        remove_time = self._nvme_remove_time.get(nvme)
        if remove_time is not None:
            # we already remove
            return 0

        _pci_rm(nvme, pci_addr)
        self._nvme_remove_time[nvme] = time.time()
        return 1



    def _pci_rescan(self, nvme):
        sec_between_remove_and_rescan = 2

        def _rescan(nvme):
            logger.info("rescan. reason nvme(%s) been removed more then 2 sec ago", nvme)
            if not self._dry_run:
                with open("/sys/bus/pci/rescan", "w") as f:
                    f.write("1")

            self._nvme_rescan_time[nvme] = time.time()


        if self._simulated_mode:
            time.sleep(sec_between_remove_and_rescan)
            _rescan(nvme)
            return 1

        remove_time = self._nvme_remove_time.get(nvme)
        if remove_time is None or time.time() - remove_time < sec_between_remove_and_rescan:
            return 0

        _rescan(nvme)
        del self._nvme_remove_time[nvme]
        return 1



    def _identify_nvme_pci_addr(self, nvme):
        _path = os.path.join("/sys/class/nvme", nvme, "address")
        res = None

        # try read from sysfs
        if os.path.exists(_path):
            try:
                with open(_path, "r") as f:
                    res = f.read().strip(' \n\t')
                # logger.debug("got %s address %s from %s", nvme, res, _path)
            except Exception as e:
                logger.exception("failed read pci addr from sysfs")

        if res is None or len(res) == 0:
            res = self._nvme_to_pci_addr.get(nvme, "")
        return res


    def _nvme_check(self, nvme):
        rescan_time = self._nvme_rescan_time.get(nvme)
        # this case the first time we check before trying to remove and rescan
        if rescan_time is None:
            return True

        # we initiate rescan but not pass 5 sec yet
        if time.time() - rescan_time <= 5:
            return False

        # we initiate rescan and 5 sec pass
        del self._nvme_rescan_time[nvme]
        return True


    def _kernel_driver_name(self, nvme, pci_addr):
        _path = f"/sys/bus/pci/devices/{pci_addr}/driver"
        try:
            if not os.path.exists(_path):
                logger.warning("path %s not exist. nvme(%s) pci_addr(%s)", _path, nvme, pci_addr)
                return ""
            driver_name = os.path.basename(os.readlink(_path))
            logger.info("driver of nvme(%s) pci_addr(%s) %s", nvme, pci_addr, driver_name)
            return driver_name
        except Exception as e:
            logger.exception("failed to identify kernel driver for nvme(%s) pci_addr(%s)", nvme, pci_addr)
        return ""


    def _nvme_ok(self, nvme):
        pci_addr = self._identify_nvme_pci_addr(nvme)
        try:
            if len(pci_addr) == 0:
                return False

            driver_name = self._kernel_driver_name(nvme, pci_addr)
            if driver_name == "nvme":
                nvme_dev_ns = [dev for dev in os.listdir("/dev") if dev.startswith(f"{nvme}n")]
                dev_path = os.path.join("/dev", nvme)
                dev_path_exist = os.path.exists(dev_path)

                logger.info("nvme(%s) pci_addr(%s) %s %s exists, namespaces(%s)", nvme, pci_addr, dev_path, "" if dev_path_exist else "not", nvme_dev_ns)

                # check nvme device exist and we have namespaces for the device
                if dev_path_exist and len(nvme_dev_ns) > 0:
                    logger.info("recovered nvme(%s) pci_addr(%s)", nvme, pci_addr)
                    self._weka_event_nvme_recovered(nvme, pci_addr)
                    return True

                # this case:
                # 1. kernel did not yet created the device and namespaces
                #
                # 2. we lost the race with wekanode
                # 2.a. the driver is nvme
                # 2.b. wekanode change it to igb_uio/vfio-pci and the device and namespaces removed
                # 2.c. we failed to find the device and the namespace.
                logger.warning("driver is nvme but no device or no namespaces nvme(%s) pci_addr(%s)", nvme, pci_addr)
                return False

            if driver_name in ["igb_uio", "vfio-pci"]:
                self._weka_event_nvme_recovered(nvme, pci_addr)
                return True

        except Exception as e:
            logger.exception("failed to identify nvme ok nvme(%s) pci_addr(%s)", nvme, pci_addr)

        return False


    def handle_nvmes(self):
        did_something = 0
        if len(self._failed_nvme_list) < 1:
            return did_something

        nvmes_to_handle = self._failed_nvme_list
        self._failed_nvme_list = []
        while len(nvmes_to_handle) > 0:
            nvme = nvmes_to_handle.pop(0)

            pci_addr = self._identify_nvme_pci_addr(nvme)
            if pci_addr is None or len(pci_addr) == 0:
                logger.error("can't identify nvme(%s) pci_addr", nvme)
                self._failed_nvme_list.append(nvme)
                continue

            logger.info("handle nvme(%s) pci_addr(%s)", nvme, pci_addr)
            if self._nvme_ok(nvme):
                continue

            if not self._nvme_check(nvme):
                self._failed_nvme_list.append(nvme)
                continue

            # nvme device not ok, keep it on the list to verify
            self._failed_nvme_list.append(nvme)

            did_something += self._nvme_remove(nvme, pci_addr)
            did_something += self._pci_rescan(nvme)

        return did_something


    def avoid_oom_killer(self):
        logger.info("setting /proc/self/oom_score_adj to -900 to avoid oom killer")
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("-900")


    def watch(self):
        self.avoid_oom_killer()

        watch_lap_time_sec = 1
        time_prev = 0
        did_something = 0
        while True:
            try:
                time_cur = time.time()

                # this sleep required to not reach core 100% while we have nothing to do
                if did_something == 0 and time_cur - time_prev < watch_lap_time_sec:
                    sleep_time = watch_lap_time_sec - (time_cur - time_prev)
                    time.sleep(sleep_time)

                did_something = 0
                try:
                    did_something += self.poll()
                except Exception as e:
                    logger.exception("something went wrong while polling")

                try:
                    did_something += self.handle_nvmes()
                except Exception as e:
                    logger.exception("something went wrong while try to handle nvmes failures")

                time_prev = time_cur

                self._verify_weka_sent_events()

                # this case useful in test scenario that nothin else left to parse and we want to bail out
                if did_something == 0 and self._file_handler.closed and len(self._failed_nvme_list) == 0:
                    logger.info("nothing left to do. exiting...")
                    return

            except Exception as e:
                logger.exception("something went wrong")


# on host restart update _test_dmesg_output with ths output of the following:
#   for i in {0..4};do printf  '0,0,0,-;nvme nvme%s: pci function %s\n0,0,0,-;nvme nvme%s: Removing after probe failure status: -19\n' "${i}" "$(cat /sys/class/nvme/nvme${i}/address)" "${i}";done
_test_dmesg_output = \
"""\
0,0,0,-;nvme nvme0: pci function 0000:00:13.0
0,0,0,-;nvme nvme0: Removing after probe failure status: -19
0,0,0,-;nvme nvme1: pci function 0000:00:16.0
0,0,0,-;nvme nvme1: Removing after probe failure status: -19
0,0,0,-;nvme nvme2: pci function 0000:00:15.0
0,0,0,-;nvme nvme2: Removing after probe failure status: -19
0,0,0,-;nvme nvme3: pci function 0000:00:14.0
0,0,0,-;nvme nvme3: Removing after probe failure status: -19
0,0,0,-;nvme nvme4: pci function 0000:00:17.0
0,0,0,-;nvme nvme4: Removing after probe failure status: -19
"""


def main_simulate_dry_run():
    handler = io.StringIO(_test_dmesg_output)
    PCIWatchDog(handler, ignore_timestamp=True, dry_run=True).watch()


def main_simulate():
    handler = io.StringIO(_test_dmesg_output)
    PCIWatchDog(handler, ignore_timestamp=True, dry_run=False).watch()


def _setup_weka_containers():
    def patch_cleanup_script(path):
        lines = None
        with open(path, "r") as f:
            lines = f.readlines()

        if lines is None or len(lines) == 0:
            raise Exception(f"failed read from {path}")

        logger.info("comment out last line of %s", path)
        lines[-1] = "#" + lines[-1]
        with open(path, "w") as f:
            f.writelines(lines)

    def is_nvme_cleanup_script(path):
        if not os.path.exists(path):
            return False

        lines = None
        with open(path, "r") as f:
            lines = f.readlines()

        if lines is None or len(lines) == 0:
            return False

        # expecting to find in last line
        # echo "0000:00:15.0" > "/sys/bus/pci/drivers/nvme/bind" || exit 3
        return "/sys/bus/pci/drivers/nvme/bind" in lines[-1]


    cmd_get_drive_containers = "weka cluster process -F hostname=$(hostname) -o container,role --no-header | grep DRIVES | awk '{print $1}'"
    containers_names = subprocess.check_output(cmd_get_drive_containers, shell=True).decode("utf-8").splitlines()
    cleanup_scripts_dir = "/opt/weka/data/agent/tmpfss/cleanup"

    container=containers_names[0]
    re_fmt = re.compile(f'^{container}_\d+_pci_(.+\d+)$')
    cleanup_script = None
    pci_addr = None
    for f in os.listdir(cleanup_scripts_dir):
        res = re_fmt.match(f)
        if res is not None and len(res.groups()) == 1:
            tmp_pci_addr = res.groups()[0].strip(' \n\t')
            tmp_script = os.path.join(cleanup_scripts_dir, f)
            if is_nvme_cleanup_script(tmp_script):
                pci_addr = tmp_pci_addr
                cleanup_script = tmp_script
                break

    if pci_addr is None or cleanup_script is None:
        raise Exception(f"failed find cleanup script for container {container}. try 'weka local start'")

    logger.info("patch containt %s cleanup script %s", container, cleanup_script)
    patch_cleanup_script(cleanup_script)

    nvme = None
    nvme_devices = [f for f in os.listdir("/dev") if f.startswith("nvme")]
    for i in range(100):
        if f"nvme{i}" not in nvme_devices:
            nvme = f"nvme{i}"
            break

    if nvme is None:
        raise Exception("failed to expect nvme device name")

    logger.info("container(%s) nvme(%s) pci_addr(%s)", container, nvme, pci_addr)
    return container, nvme, pci_addr


def _fake_weka_drive_failure():
    def kmsg_write(msg):
        with open("/dev/kmsg", "w") as f:
            f.write(msg)
            f.flush()

    container, nvme, pci_addr = _setup_weka_containers()

    logger.info("stop container(%s)", container)
    subprocess.Popen(["weka", "local", "stop", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).communicate()
    while True:
        lines = subprocess.check_output(["weka", "local", "ps", "-F", f"state=Stopped,name={container}", "-o", "name", "--no-header"]).decode("utf-8").splitlines()
        if lines is None or len(lines) != 1 or lines[0].strip(' \n\t') != container:
            time.sleep(1)
            continue
        break

    logger.info("start container(%s)", container)
    subprocess.Popen(["weka", "local", "start", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).communicate()
    while True:
        lines = subprocess.check_output(["weka", "local", "ps", "-F", f"state=Running,name={container}", "-o", "name", "--no-header"]).decode("utf-8").splitlines()
        if lines is None or len(lines) != 1 or lines[0].strip(' \n\t') != container:
            time.sleep(1)
            continue
        break

    kmsg_write(f"nvme {nvme}: pci function {pci_addr}\n")
    kmsg_write(f"nvme {nvme}: Removing after probe failure status: -19\n")



def main(simulate_drive_fault=False):
    try:
        with open("/dev/kmsg", "r") as f:
            logger.info("opened /dev/kmsg")
            dog = PCIWatchDog(f)

            if simulate_drive_fault:
                _fake_weka_drive_failure()

            dog.watch()

    except KeyboardInterrupt:
        pass

    logger.info("bye bye")


if __name__ == '__main__':
    # main_simulate_dry_run()
    # main_simulate()
    main()
