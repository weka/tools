# bios_tool
A tool for viewing/setting bios_settings for Weka servers

```angular2html

usage: bios_tool.py [-h] [-c [HOSTCONFIGFILE]] [-b [BIOS]] [--fix] [--reboot] [--dump] [--diff DIFF DIFF] [-v]

View/Change BIOS Settings on servers

optional arguments:
  -h, --help            show this help message and exit
  -c [HOSTCONFIGFILE], --hostconfigfile [HOSTCONFIGFILE]
                        filename of host config file
  -b [BIOS], --bios [BIOS]
                        bios configuration filename
  --fix                 Correct any bios settings that do not match the definition
  --reboot              Reboot server if changes have been made
  --dump                Print out BIOS settings only
  --diff DIFF DIFF      Compare 2 hosts
```

## Getting Started
There are 2 configuration files for bios_tool: a host configuration file ("host_config.yml") and a BIOS settings configuration file ("bios_config.yml")
You can either use these default names or override the configuration file names using the provided command-line switches, -c/--hostconfigfile and -b/--bios.
### host_config.yml
The host_config.yml defines the list of hosts, and their logon credentials for the BMC (ipmi, iLO, iDRAC).

The format standard YAML, as such:
```angular2html
hosts:
  # Hpe servers
  - name: 172.29.3.1
    user: Administrator
    password: Administrator
  - name: 172.29.3.2
    user: Administrator
    password: Administrator
```
You should set all the servers you want to work with here.   Note they may have different passwords for each server.

### bios_config.yml
The bios_config.yml defines the BIOS settings that you want set on the servers that are defined in the host_config.yml file.

Again, the format is standard YAML, as such:
```angular2html
server-manufacturer:
  architecture:
    setting: value
    setting: value
  architecture2:
    setting: value
    setting: value
```
The server-manufacturer is matched to the manufacturer ("Oem") listed in the RedFish data so this tool can be used with any manufacturer that supports RedFish.
Currently known manufacturer names are "Dell", "Hpe", and "Supermicro" and defaults for these manufacturers are in the example file.

The architecture can be either "AMD" or "Intel".   No other architectures are currently supported.

See the provided bios_config.yml for a full example, but here's what it looks like:
```angular2html
Dell:
  AMD: {}
  Intel:
    PackageCStates: Enabled
    ProcC1E: Disabled
    ProcCStates: Disabled
    ProcPwrPerf: MaxPerf
    SecureBoot: Disabled
    SriovGlobalEnable: Enabled
    SubNumaCluster: Disabled
    WorkloadConfiguration: Balance
    WorkloadProfile: NotConfigured
```

## Default Behavior
With no command-line overrides, bios_tool will scan the hosts in the host_config.yml and note where they differ (if they differ) from the settings in the bios_settings.yml file.
No changes are made to the servers (read-only mode)

## Optional Behaviors
### Fix Mode
Using the --fix command line option will cause the tool to make the settings to the bios as defined in the bios_settings.yml.   
It will not reboot the server(s) unless given the --reboot option
### Reboot option
Using a --reboot with --fix will make bios_tool reboot the servers after any changes are made.  
Only servers that have been modified are rebooted (this causes them to APPLY the changes)
### Dump option
Using the --dump command line option will cause the tool to simply print out all the bios settings for each server. (read-only)
### Diff option
Using the --diff option will compare all the settings on 2 servers, and print out which settings differ.
