from src.common import bcolors, global_vars
from src.helpers import get_arguments, set_args
import src.steps as steps


def do_migrate():
    if not global_vars.skip_checks:
        steps.system_health_check()
        steps.preliminary_check()
    steps.enter_migration_mode()
    steps.enter_drain_mode()
    steps.migrate_data()
    steps.validate_migration()
    steps.drain_and_restarts_all_hosts()
    steps.validate_kwas_is_up()
    steps.exit_migration_mode()
    steps.remove_etcd_internals()


if __name__ == '__main__':
    args = get_arguments()
    set_args(args)
    do_migrate()
    print(f"{bcolors.GREEN}{bcolors.BOLD}MIGRATION COMPLETED SUCCESSFULLY{bcolors.ENDC}")

