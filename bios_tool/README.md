# bios_tool
A tool for viewing/setting bios_settings for Weka servers

```angular2html

usage: bios_tool [-h] [-c [HOSTCONFIGFILE]] [-b [BIOS]] [--bmc_config] [--fix] [--reboot] [--dump] [--reset_bios] [--diff DIFF DIFF] [--bmc_ips [BMC_IPS ...]]
                 [--bmc_username BMC_USERNAME] [--bmc_password BMC_PASSWORD] [-v] [--version]

View/Change BIOS Settings on servers

optional arguments:
  -h, --help            show this help message and exit
  -c [HOSTCONFIGFILE], --hostconfigfile [HOSTCONFIGFILE]
                        filename of host config file
  -b [BIOS], --bios [BIOS]
                        bios configuration filename
  --bmc_config          Configure the BMCs to allow RedFish access
  --fix                 Correct any bios settings that do not match the definition
  --reboot              Reboot server if changes have been made
  --dump                Print out BIOS settings only
  --reset_bios          Reset BIOS to default settings. To also reboot, add the --reboot option
  --diff DIFF DIFF      Compare 2 hosts BIOS settings
  --bmc_ips [BMC_IPS ...]
                        a list of hosts to configure, or none to use cluster beacons
  --bmc_username BMC_USERNAME
                        a username to use on all hosts in --bmc_ips
  --bmc_password BMC_PASSWORD
                        a password to use on all hosts in --bmc_ips
  -v, --verbose         enable verbose mode
  --version             report program version and exit

```

## Getting Started
There are 2 configuration files for bios_tool: a host configuration file ("host_config.yml" or host_config.csv) and a BIOS settings configuration file ("bios_config.yml")
You can either use these default names or override the configuration file names using the provided command-line switches, -c/--hostconfigfile and -b/--bios or --bmc_ips.  (see Optional Behaviors/Command-line Host Specification below for --bmc_ips)
### host_config.yml or csv
The host_config.yml/csv defines the list of hosts, and their logon credentials for the BMC (ipmi, iLO, iDRAC).  This may be in YAML or CSV format.  Use the file extension `.yml` or `.csv` to indicate the format.

The format can be standard CSV, as such: (compatible with Excel)
```angular2html
name,user,password
172.29.3.164,ADMIN,_PASSWORD_1!
172.29.3.1,Administrator,Administrator
172.29.1.74,root,Administrator
172.29.1.75,root,Administrator
```

The format can also be standard YAML, as such:
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

See the section on `--bcm_ips` to configure the hosts on the command line instead of in configuration files.

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

Note that we've prvovided 2 examples - a standard set of BIOS settings, and a set specifically for Dell AMD with Genoa processors.

## Default Behavior
With no command-line overrides, bios_tool will scan the hosts in the host_config.yml and note where they differ (if they differ) from the settings in the bios_settings.yml file.
No changes are made to the servers (read-only mode)

Example output:
```angular2html
Fetching BIOS settings of host 172.29.3.1
Fetching BIOS settings of host 172.29.3.2
Fetching BIOS settings of host 172.29.3.3
[...snip...]
No changes are needed on 172.29.3.1
No changes are needed on 172.29.3.2
No changes are needed on 172.29.3.3
[...snip...]
172.29.3.4: BIOS setting ApplicationPowerBoost is Enabled, but should be Disabled
172.29.3.4: BIOS setting CStateEfficiencyMode is Enabled, but should be Disabled
172.29.3.4: BIOS setting DataFabricCStateEnable is Auto, but should be Disabled
172.29.3.4: BIOS setting DeterminismControl is DeterminismCtrlAuto, but should be DeterminismCtrlManual
[...snip...]
```

## Optional Behaviors
### BMC Configuration mode
Using the --bms_config command line option will cause bios_tool to ssh to each of the servers and turn on RedFish and IPMI Over LAN.   The RedFish is strictly REQUIRED for bios_tool operation.   IPMI Over LAN is required for WMS deployment to operate properly, so is automatically enabled.
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

Example diff output:
```angular2html
Fetching BIOS settings of host 172.29.3.1
Fetching BIOS settings of host 172.29.3.6

Settings that are different between the servers:
Setting                     172.29.3.1                 172.29.3.6
--------------------------  -------------------------  ----------------------------
ApplicationPowerBoost       Disabled                   Enabled
CStateEfficiencyMode        Disabled                   Enabled
DataFabricCStateEnable      Disabled                   Auto
DeterminismControl          DeterminismCtrlManual      DeterminismCtrlAuto
InfinityFabricPstate        P0                         Auto
MinProcIdlePower            NoCStates                  C6
NumaGroupSizeOpt            Clustered                  Flat
NumaMemoryDomainsPerSocket  TwoMemoryDomainsPerSocket  Auto
PerformanceDeterminism      PerformanceDeterministic   PowerDeterministic
PowerRegulator              StaticHighPerf             OsControl
ProcAmdIoVt                 Disabled                   Enabled
ProcSMT                     Disabled                   Enabled
SerialNumber                MXQ2201FNK                 MXQ2201FND
Sriov                       Disabled                   Enabled
ThermalConfig               IncreasedCooling           OptimalCooling
WorkloadProfile             I/OThroughput              GeneralPowerEfficientCompute
```
### Command-line Host Specification
Using --bmc_ips with a space separated list of IP addresses (ie: `--bmc_ips 192.168.1.1 192.168.1.2`) and --bmc_username and --bmc_password will allow you to easily configure a set of servers that have the same userid/password settings, rather than providing a configuration file.
### Version option
Using --version will simply print the bios_tool version number and exit.
