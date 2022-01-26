#!/usr/bin/env python3

# docs are here: https://wekaio.atlassian.net/wiki/spaces/SUP/pages/1565032485/How+to+change+cores+allocation+at+runtime

import json
import os
import shlex
import subprocess
import sys

def main(argv):
    if len(argv) != 4:
        print('Usage: ./{} <cores> <drives-dedicated-cores> <frontend-dedicated-cores>'.format(os.path.basename(__file__)))
        exit(1)

    cores, drive_cores, fe_cores = [int(count) for count in argv[1:]]
    compute_cores = cores - fe_cores - drive_cores
    print("""Will configure a total of {} cores:
\t{} DRIVES nodes
\t{} COMPUTE nodes
\t{} FRONTEND nodes
""".format(cores, drive_cores, compute_cores, fe_cores))

    # Backing up resources without use of `weka local resources export` because on 3.8.1 it does not exist
    backup_file_name = os.path.abspath('resources.json.backup')
    if os.path.exists(backup_file_name):
        print("Backup resources file {} already exists, will not override it".format(backup_file_name))
        exit(1)

    backup_resources_command = '/bin/sh -c "weka local resources -J > {}"'.format(backup_file_name)
    print("Backing up resources to {}".format(os.path.abspath(backup_file_name)))
    process = subprocess.Popen(shlex.split(backup_resources_command), stdout=subprocess.PIPE)
    output, stderr = process.communicate()
    if process.returncode != 0:
        print("Something went wrong when backing up resources")
        print("Return Code: {}".format(process.returncode))
        print("Output: {}".format(output))
        print("Stderr: {}".format(stderr))
        exit(1)

    # Read content of the backup file - these are the current resources
    with open(backup_file_name, 'r') as f:
        prev_resources = json.loads(f.read())

    core_change_command = '/bin/sh -c "weka local resources cores {} --drives-dedicated-cores={} --frontend-dedicated-cores={}"'.format(cores, drive_cores, fe_cores)
    print("Staging a core configuration change using the following command: {}".format(core_change_command))
    process = subprocess.Popen(shlex.split(core_change_command), stdout=subprocess.PIPE)
    output, stderr = process.communicate()
    if process.returncode != 0:
        print("Something went wrong when backing up resources")
        print("Return Code: {}".format(process.returncode))
        print("Output: {}".format(output))
        print("Stderr: {}".format(stderr))
        exit(1)

    export_file_name = os.path.abspath('resources.json.tmp')
    export_resources_command = '/bin/sh -c "weka local resources -J > {}"'.format(export_file_name)
    print("Exporting resources to {}".format(os.path.abspath(export_file_name)))
    process = subprocess.Popen(shlex.split(export_resources_command), stdout=subprocess.PIPE)
    output, stderr = process.communicate()
    if process.returncode != 0:
        print("Something went wrong when exporting resources")
        print("Return Code: {}".format(process.returncode))
        print("Output: {}".format(output))
        print("Stderr: {}".format(stderr))
        exit(1)

    # Read content of the file with changed cores
    with open(export_file_name, 'r') as f:
        staged_resources = json.loads(f.read())

    # Preserve the rpc_port of these resources
    for slot in staged_resources['nodes']:
        staged_resources['nodes'][slot]['rpc_port'] = prev_resources['nodes'][slot]['rpc_port']

    print("Staged changes:")
    for slot in staged_resources['nodes']:
        node = staged_resources['nodes'][slot]
        print("\t%02d rpc_port=%s roles=%s" % (int(slot), node['rpc_port'], node['roles']))
    print("")

    # Write the staged changes to the export_file_name
    with open(export_file_name, 'w') as f:
        f.write(json.dumps(staged_resources))

    import_resources_command = '/bin/sh -c "weka local resources import {} -f"'.format(export_file_name)
    print("Importing resources from {}".format(os.path.abspath(export_file_name)))
    process = subprocess.Popen(shlex.split(import_resources_command), stdout=subprocess.PIPE)
    output, stderr = process.communicate()
    if process.returncode != 0:
        print("Something went wrong when importing resources")
        print("Return Code: {}".format(process.returncode))
        print("Output: {}".format(output))
        print("Stderr: {}".format(stderr))
        exit(1)

    apply_resources_command = '/bin/sh -c "weka local resources apply -f"'.format(export_file_name)
    print("Applying resources using local apply command")
    process = subprocess.Popen(shlex.split(apply_resources_command), stdout=subprocess.PIPE)
    output, stderr = process.communicate()
    if process.returncode != 0:
        print("Something went wrong when applying resources")
        print("Return Code: {}".format(process.returncode))
        print("Output: {}".format(output))
        print("Stderr: {}".format(stderr))
        exit(1)

    print("\nFinished applying core configuration")


if '__main__' == __name__:
    main(sys.argv)
