from enum import Enum


class SharedData:
    s3_hosts = {}
    migrate_host = ""
    migrate_host_id = 0
    auto_mode = 1
    socket_path = ""
    socket_prefix = "/data/cross-container-rpc/"
    socket_extension = ".sock"
    step_number = 1
    skip_checks = False


global_vars = SharedData()


class bcolors:
    VIOLET = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ENDC = '\033[0m'
    DARK_GREEN = '\033[32m'


class Automode(Enum):
    MANUAL = 0
    SEMI = 1
    AUTO = 2
