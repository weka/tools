import json
import time

from src.common import bcolors, global_vars, Automode
from src.helpers import set_drain_mode, get_migration_status, print_errors_dict, wait_for_drain, send_bash_command, \
    send_request, continue_to_next_step, continue_to_next_host, is_client_running_on_host, is_etcd_up_and_working, \
    validate_set_migration_read_only_mode, validate_host_in_migration_read_only_mode, is_host_ready


def step(step_str, force_lower_auto_mode=False):
    def wrap(f):
        def wrapped_f(*args):
            print(f"{bcolors.VIOLET}{bcolors.BOLD}Step {global_vars.step_number}: {step_str}{bcolors.ENDC}")
            global_vars.step_number += 1
            if global_vars.auto_mode != Automode.AUTO.value or force_lower_auto_mode:
                if not continue_to_next_step():
                    do_revert()

            f(*args)
        return wrapped_f
    return wrap


@step("Running preliminary checks on current system")
def system_health_check():
    output = send_bash_command("weka s3 cluster status -J")
    hosts_health = json.loads(output)
    for key, value in hosts_health.items():
        if (int(''.join(filter(str.isdigit, key))) in global_vars.s3_hosts.values()) and not value:
            print(
                f"{bcolors.RED}ERROR: host {key} is not ready, you can use the hosts argument to "
                f"run the script only on selected hosts.{bcolors.ENDC}")
            exit(1)
    print(f"{bcolors.DARK_GREEN}\tAll S3 hosts are ready{bcolors.ENDC}")

    for host in global_vars.s3_hosts.keys():
        r = send_request(f"http://{host}:9001/minio/upgrade/mode")
        if r.content != b"{'Mode':'false'}":
            print(f"{bcolors.RED}ERROR: Host {host} is in Upgrade Mode. Fix what is needed and re-run script{bcolors.ENDC}")
            exit(1)
    print(f"{bcolors.DARK_GREEN}\tAll S3 hosts are not in Upgrade Mode{bcolors.ENDC}")

    is_etcd_up_and_working()
    print(f"{bcolors.DARK_GREEN}\tAll S3 hosts loaded successfully their ETCD data{bcolors.ENDC}")

    for host in global_vars.s3_hosts.keys():
        output = send_bash_command(f"ssh {host} weka local exec -C s3 ls {global_vars.socket_path}").decode("utf-8").rstrip('\n')
        if output != global_vars.socket_path:
            print(f"{bcolors.RED}ERROR: Host {host} is missing it's socket file. Fix what is needed and re-run script{bcolors.ENDC}")
            exit(1)
    print(f"{bcolors.DARK_GREEN}\tAll S3 hosts contains their socket{bcolors.ENDC}")

    print(f"{bcolors.GREEN}\tAll hosts are healthy.{bcolors.ENDC}")


@step("Running preliminary checks on current database to make sure it upholds KWAS limitations")
def preliminary_check():
    r = send_request(f"http://{global_vars.migrate_host}:9001/minio/migration/preliminary-check/kwas")
    response_body = r.json()
    if response_body["verified"]:
        print(f"{bcolors.GREEN}\tPreliminary checks succeeded.{bcolors.ENDC}")
    else:
        print(f"{bcolors.RED}ERROR: Some data in current configuration isn't valid for KWAS. Fix it and run script again. The invalid data is: {bcolors.ENDC}")
        print_errors_dict(response_body["errors"])
        exit(1)


@step("Inserting S3 cluster into Migration Read Only Mode")
def enter_migration_mode(revert=False):
    rev_cmd = "force_kwas_on_minio_restart=false" if revert else ""
    for host, host_id in global_vars.s3_hosts.items():
        output = send_bash_command(f"weka debug manhole --slot 0 --host {host_id} s3_enter_kwas_migration_mode {rev_cmd}")
    time.sleep(1)
    validate_set_migration_read_only_mode(True)

    print(f"{bcolors.GREEN}\tAll S3 hosts are in Migration Read Only Mode.{bcolors.ENDC}")


@step(f"Entering host to Drain Mode")
def enter_drain_mode():
    set_drain_mode(True, global_vars.migrate_host_id)
    # add a wait for drain
    print(f"{bcolors.CYAN}\tWaiting for host {global_vars.migrate_host} to be drained. if this takes too long, cancel "
          f"script (^C) fix what is needed and re-run script{bcolors.ENDC}")
    wait_for_drain(global_vars.migrate_host)
    print(f"{bcolors.GREEN}\tHost {global_vars.migrate_host} is in Drain Mode.{bcolors.ENDC}")


@step("Migrating all of ETCD data into KWAS")
def migrate_data():
    migration_status = get_migration_status(global_vars.migrate_host)
    if migration_status["in_progress"]:
        print(f"{bcolors.RED}ERROR: migration is in progress. Fix what is needed and rerun script{bcolors.ENDC}")
        exit(1)
    data = {"kwas_endpoint": global_vars.socket_path}
    r = send_request(f"http://{global_vars.migrate_host}:9001/minio/migration/migrate/kwas", data)
    while True:
        migration_status = get_migration_status(global_vars.migrate_host)
        if not migration_status["in_progress"]:
            break
    if migration_status["error"] != "":
        print(f"{bcolors.RED}ERROR: migration failed during step {migration_status['step']} with error: "
              f"'{migration_status['error']}'. Fix what is needed and rerun script{bcolors.ENDC}")
        exit(1)
    print(f"{bcolors.GREEN}\tFinished migrating data.{bcolors.ENDC}")


@step("Validating migration")
def validate_migration():
    data = {"kwas_endpoint": global_vars.socket_path}
    r = send_request(f"http://{global_vars.migrate_host}:9001/minio/migration/validate/kwas", data).json()
    if not r['verified']:
        print(f"{bcolors.RED}ERROR: Migration Validation failed. Fix it and run script again. The invalid data is: {bcolors.ENDC}")
        print_errors_dict(r["errors"])
        exit(1)
    print(f"{bcolors.GREEN}\tAll migrated data was verified successfully{bcolors.ENDC}")


@step("Draining all S3 hosts and Restarting them into selected mode")
def drain_and_restarts_all_hosts(revert=False):
    client = "etcd" if revert else "kwas"
    mode = "old" if revert else "new"
    for host, id in global_vars.s3_hosts.items():
        if global_vars.auto_mode < Automode.AUTO.value:
            if not continue_to_next_host():
                do_revert()

        set_drain_mode(True, id)
        print(f"{bcolors.CYAN}\tWaiting for host {host} to be drained. if this takes too long, cancel "
              f"script (^C) fix what is needed and re-run script{bcolors.ENDC}")
        wait_for_drain(host)
        print(f"{bcolors.DARK_GREEN}\tHost {host} is in Drain Mode, Restarting it into {mode} mode{bcolors.ENDC}")

        output = send_bash_command(f"weka debug manhole --slot 0 --host {id} "
                                   f"s3_update_config force_minio_refresh=true")
        while True:
            time.sleep(2)
            if is_host_ready(id):
                break
        if not validate_host_in_migration_read_only_mode(host, "enter"):
            print(f"{bcolors.RED}ERROR: Host {host} is not in Migration Read Only Mode.{bcolors.ENDC}")
            exit(1)
        if not is_client_running_on_host(client, host):
            print(f"{bcolors.RED}ERROR: Host {host} is not running with {client}. Fix it and run script again.{bcolors.ENDC}")
            exit(1)

    print(f"{bcolors.GREEN}\tAll hosts are Ready.{bcolors.ENDC}")


@step("Validating all minIOs are up with KWAS")
def validate_kwas_is_up():
    for host in global_vars.s3_hosts.keys():
        if not is_client_running_on_host('kwas', host):
            print(f"{bcolors.RED}ERROR: Not all minIOs are up with kwas. Fix it and run script again.{bcolors.ENDC}")
            exit(1)
    print(f"{bcolors.GREEN}\tAll hosts are Ready with KWAS.{bcolors.ENDC}")

    print(f"{bcolors.YELLOW}{bcolors.BOLD}After this step, rolling back to ETCD is no longer supported. "
          f"Meaning this is the step after which the S3 cluster is forever KWAS.{bcolors.ENDC}")


@step("Exiting S3 cluster from Migration Read Only Mode")
def exit_migration_mode():
    for host, id in global_vars.s3_hosts.items():
        output = send_bash_command(f"weka debug manhole --slot 0 --host {id} s3_exit_kwas_migration_mode")
    time.sleep(1)
    validate_set_migration_read_only_mode(False)

    print(f"{bcolors.GREEN}\tAll S3 hosts exited Migration Read Only Mode.{bcolors.ENDC}")


@step("Stopping ETCD from running, and Changing minIO defaults to KWAS")
def remove_etcd_internals():
    print(f"{bcolors.CYAN}\tSetting etcd-enable configuration to false.{bcolors.ENDC}")
    output = send_bash_command(f"weka s3 cluster update --etcd-enable=off")

    print(f"{bcolors.CYAN}\tValidating etcd-enable configuration is false.{bcolors.ENDC}")
    output = send_bash_command("weka debug config show s3ClusterInfo.etcdEnabled").decode("utf-8")

    if output.find("false") == -1:
        print(f"{bcolors.RED}ERROR: s3ClusterInfo.etcdEnabled was not set properly to false.{bcolors.ENDC}")
        exit(1)

    print(f"{bcolors.CYAN}\tWaiting 20 seconds on each host to make sure ETCD isn't starting.{bcolors.ENDC}")
    for host in global_vars.s3_hosts.keys():
        output = send_bash_command(f"ssh {host} weka local exec -C s3 supervisorctl stop etcd")
        t_end = time.time() + 20
        while time.time() < t_end:
            time.sleep(1)
            output = send_bash_command(f"ssh {host} weka local exec -C s3 ps -elf")
            if 'etcd' in output.decode("utf-8"):
                print(f"{bcolors.RED}ERROR: ETCD is running on host {host} after being brought down.{bcolors.ENDC}")
                exit(1)

    print(f"{bcolors.GREEN}\tKWAS set to default, current etcd clients stopped.{bcolors.ENDC}")


@step("Validating revert")
def post_revert_validations():
    for host in global_vars.s3_hosts.keys():
        if not is_client_running_on_host('etcd', host):
            print(f"{bcolors.RED}ERROR: Not all minIOs are up with etcd. {bcolors.ENDC}")
            exit(1)
    is_etcd_up_and_working()


def do_revert():
    global_vars.step_number = 1
    global_vars.auto_mode = 2
    print(f"{bcolors.YELLOW}{bcolors.BOLD}Starting Revert{bcolors.ENDC}")

    enter_migration_mode(True)
    drain_and_restarts_all_hosts(True)
    exit_migration_mode()
    post_revert_validations()
    print(f"{bcolors.GREEN}Revert finished successfully{bcolors.ENDC}")
    exit(0)
