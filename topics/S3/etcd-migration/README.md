# ETCD to KWAS Migration Tool

Easy migration from ETCD to KWAS script

## Basic Idea

This script follows the step described in the [manual migration process](https://www.notion.so/wekaio/Official-field-etcd-kwas-migration-procedure-0f2cc972853e44ad918b5e696d0c78cf) in order to automate and ease the procedure.


## Usage

The `main.py` script can be called with no args (default of semi-automated mode will be used) or with args explained in the help message (described below)

### Help Message

```text
usage: ETCD to KWAS Migration [-h] [-a AUTO_MODE] [-s HOSTS]
                              [-f FRONTEND_CONTAINER_NAME] [-t]

optional arguments:
  -h, --help            show this help message and exit
  -a AUTO_MODE, --auto-mode AUTO_MODE
                        Automated Level [0-2] where 0 is manual mode. default
                        is 1 (semi-automated)
  -s HOSTS, --hosts HOSTS
                        S3 hosts in cluster (this field is mandatory in manual
                        mode)
  -f FRONTEND_CONTAINER_NAME, --frontend-container-name FRONTEND_CONTAINER_NAME
                        S3 manager container name (this field is mandatory in
                        manual mode)
  -t, --skip-checks     Skip preliminary checks

```

### Usage Examples

*Run with default semi-automated mode:* `python3 auto-migrate/main.py`

*Run in manual mode:* `python3 auto-migrate/main.py -a 0 -f frontend0 -s "test-0" "test-1" "test-3" "test-4"`

*Run with no preliminary checks and in fully automated mode:* `python3 auto-migrate/main.py -a 2 -t`

## Installation

The script requires python >=3.7. \
It also relies on external dependencies, to easily install them run `python3 -m pip install -r requirements.txt` 

## After Migrations Tips:

After the script finishes successfully, User should verify successful sync of data by performing validation steps that are mentioned in the manual notion guide,
this includes to 'Perform IOs to test policy mapping sync'
