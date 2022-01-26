#!/usr/bin/env python3

#
# Configure a cluster
#   Expects the hosts to be in STEM mode already
#
#   Written by Vince Fleming, vince@weka.io
#


#
# imports
#
import subprocess
from subprocess import Popen, PIPE, STDOUT
import sys
import json
import os.path
import os
from datetime import datetime
import argparse
import time
import re

###################################################################################################################
#
# Weka constants
#
def_ram_per_core = 1434 # per core
max_cores = 19      # per host

###################################################################################################################
#
# Class definitions
#
class Drive:
    def __init__(self, name, path, size, nvme):
        self.name = name
        self.path = path
        self.size = size
        self.isNvme = nvme

class IPInterface:
    def __init__(self, ifname, linklayer, ipaddr, mtu, description, speed):
        self.ifname = ifname
        self.linklayer = linklayer          # ETH or IB
        self.ipaddr = ipaddr                # ip address set in the OS
        self.mtu = mtu
        self.description = description
        self.gateway = None
        self.netmask = None
        self.network = None
        self.speed = speed
        #self.ip_range = None                # only used if setting a range of IPs per interface (instead of default-net)
        #self.range_mask = None

class WekaHost:

    def __init__(self, hostname):
        self.name = hostname
        self.hostid = -1
        self.ipifs = {}             # a dict of ifname:IPInterface obj
        self.drives = {}            # a dict of drivename:size
        self.server_mgmt_ip = None  # server management ip addr (typically not on dataplane)
        self.weka_mgmt_ip = []      # weka management ip addr (always on dataplane) - there may be 2 of them
        self.mgmt_ip = None         # what is the weka mangement ip address?
        self.total_cores = 0        # Total cores on this host
        self.fe_cores = 0           # Front End Cores on this host
        self.drives_cores = 0       # Drives cores on this host
        self.bp_cores = 0           # Best Practices # of cores
        self.usable_cores = 0       # Usable cores on this host
        self.memory = 0             # total physical memory in MB
        self.usable_mem = 0         # usable memory in MB
        self.weka_memory = 0        # weka memory to set on this host
        self.wekaversion = ""


class WekaCluster:

    def __init__(self):
        self.name = None
        self.hosts = {}     # dict of host hostname: WekaHost objects
        self.cloudenable = True
        self.isdedicated = True
        self.isIB = False
        self.parity = 2     # number of parity nodes
        self.data = 0       # number of data nodes
        self.hot_spares = 0 # number of hot spare nodes
        self.aws = False
        self.ip_range = None
        self.range_mask = None
        self.dataplane_mgmt = False

###################################################################################################################
#
# Functions
#
try:
    input = raw_input
except NameError:
    pass

def prompt( message, default_answer, errormessage, isvalid, isvalid_arg ):
    res = None
    while res is None:
        if default_answer is not None:
            res = input(str(message)+ '(' + str(default_answer) + '): ')
        else:
            res = input(str(message)+ ': ')

        if (len(res) == 0) and default_answer is not None:
            res = default_answer
        if not isvalid( res, isvalid_arg ):
            print( str(errormessage) )
            res = None
    return res

def prompt_yn( message, default_answer ):
    response = prompt( message, default_answer, "\tPlease respond Y/y or N/n", checkyn, None )
    if response.lower() == "y":
        return True
    else:
        return False

def checkcores( num_cores, host ):
    if int(num_cores) > host.usable_cores:
        return False
    if int(num_cores) == host.bp_cores:
        return True
    if host.usable_mem / int(num_cores) < 7680:               # 7.5GB per core is preferred/max?
        print( "\tRAM per core will be " + str(host.usable_mem / int(num_cores)) + "GiB" )
        return prompt_yn( "Are you sure? [Y/n]", "y" )
    else:
        return True         # if within guidelines, don't ask

def check_be_drives_cores( num_cores, host ):    # this should be fancier
    if int(num_cores) > host.usable_cores:
        return False
    if int(num_cores) < 0:
        return False

    # sanity check - we need at least 1 core for Compute!
    if host.total_cores <= host.fe_cores + host.drives_cores + int(num_cores):
        print( "Invalid core configuration - No Compute cores - FE cores + Drive cores must be less then Total cores." )
        return False

    return True


def checkname( name, junk ):
    # check that the cluster name is a valid string
    is_ok = True
    if len( name ) < 2:         # should also check max length
        return False
    for i in name:
        if not (i.isalnum() or i == "." or i == '-' or i == '_'):
            return False
    return True

def checkhost( hostname, junk ):
    # check that a hostname/ip is valid
    if len( hostname ) == 0:
        return False
    
    return reachable( hostname )
    #response = os.system("ping -c 1 " + hostname + " >/dev/null 2>&1")
    #return not response

def checkyn( answer, junk ):
    if answer == None:
        return False
    else:
        lowerans = answer.lower()
        return (lowerans == "y") or (lowerans == "n")
    
def check24( answer, junk ):
    if answer == None:
        return False
    else:
        return (int(answer) == 2) or (int(answer) == 4)

def checknumdrives( answer, max_drv ):
    return (int(answer) >= 3) and (int(answer) <= max_drv)   

def checknumspares( answer, max_drv ):
    return (int(answer) >= 0) and (int(answer) <= max_drv)   

def checkhostbounds( answer, junk ):
    if answer.lower() == "a":
        return True
    return answer.isdigit()

def ip_to_int( ipaddr_str ):
    parts = ipaddr_str.split( '.' )
    return (int( parts[0] ) << 24) + (int( parts[1] ) << 16) + (int( parts[2] ) << 8) + int( parts[3] )

def int_to_ip( ipaddr_int ):
    return str( ipaddr_int >> 24 ) + "." + str( (ipaddr_int & (255 << 16)) >> 16) + "." + str( (ipaddr_int & (255 << 8)) >> 8 ) + "."  + str( ipaddr_int & 255 )

def network_ip( ipaddr, maskbits ):
    int_ipaddr = ip_to_int( ipaddr )
    mask = (int( "0xffffffff", 16 ) >> (32-maskbits)) << (32-maskbits)
    return int_to_ip( int_ipaddr & mask )

def iprange_startip( ip_range ):
    splits = ip_range.split( "-" )        # "192.168.1.2-3.14" -> ["192.168.1.2", "3.14"]
    return( splits[0] )

def iprange_endip( ip_range ):
    splits = ip_range.split( "-" )        # "192.168.1.2-3.14" -> ["192.168.1.2", "3.14"]
    int_ipaddr_base = ip_to_int( splits[0] )
    base_octet_list = splits[0].split( "." )    # "192.168.1.2" -> ["192", "168", "1", "2"]
    if len( splits ) > 1:
        end_octet_list = splits[1].split( "." )    # "3.14" -> ["3", "14"]
        num_octets = len( end_octet_list )
        end_ip = []

        # reverse the lists/addresses to make this easier
        end_octet_list.reverse()
        base_octet_list.reverse()

        for octet in end_octet_list:
            end_ip.append( octet )
        for octet in base_octet_list:
            if num_octets > 0:
                num_octets -= 1
            else:
                end_ip.append( octet )
        return end_ip[3] + "." + end_ip[2] + "." + end_ip[1] + "." + end_ip[0]
    else:
        return ip_range


def iprange_num_ips( ip_range ):
    return ip_to_int( iprange_endip( ip_range ) ) - ip_to_int( iprange_startip( ip_range ) ) + 1



def is_valid_ipv4(ip):
    """Validates IPv4 addresses.
    """
    pattern = re.compile(r"""
        ^
        (?:
          # Dotted variants:
          (?:
            # Decimal 1-255 (no leading 0's)
            [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
          |
            0x0*[0-9a-f]{1,2}  # Hexadecimal 0x0 - 0xFF (possible leading 0's)
          |
            0+[1-3]?[0-7]{0,2} # Octal 0 - 0377 (possible leading 0's)
          )
          (?:                  # Repeat 0-3 times, separated by a dot
            \.
            (?:
              [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
            |
              0x0*[0-9a-f]{1,2}
            |
              0+[1-3]?[0-7]{0,2}
            )
          ){0,3}
        |
          0x0*[0-9a-f]{1,8}    # Hexadecimal notation, 0x0 - 0xffffffff
        |
          0+[0-3]?[0-7]{0,10}  # Octal notation, 0 - 037777777777
        |
          # Decimal notation, 1-4294967295:
          429496729[0-5]|42949672[0-8]\d|4294967[01]\d\d|429496[0-6]\d{3}|
          42949[0-5]\d{4}|4294[0-8]\d{5}|429[0-3]\d{6}|42[0-8]\d{7}|
          4[01]\d{8}|[1-3]\d{0,9}|[4-9]\d{0,8}
        )
        $
    """, re.VERBOSE | re.IGNORECASE)
    return pattern.match(ip) is not None

def is_valid_range(ip):
    """Validates IPv4 ranges of addresses.
    """
    pattern = re.compile(r"""
        ^
        (?:
          # Dotted variants:
          (?:
            # Decimal 1-255 (no leading 0's)
            [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
          |
            0x0*[0-9a-f]{1,2}  # Hexadecimal 0x0 - 0xFF (possible leading 0's)
          |
            0+[1-3]?[0-7]{0,2} # Octal 0 - 0377 (possible leading 0's)
          )
          (?:                  # Repeat 0-3 times, separated by a dot
            \.
            (?:
              [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
            |
              0x0*[0-9a-f]{1,2}
            |
              0+[1-3]?[0-7]{0,2}
            )
          ){0,3}
        |
          # Dotted variants with ranges:
          (?:
            # Decimal 1-255 (no leading 0's)
            [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
          |
            0x0*[0-9a-f]{1,2}  # Hexadecimal 0x0 - 0xFF (possible leading 0's)
          |
            0+[1-3]?[0-7]{0,2} # Octal 0 - 0377 (possible leading 0's)
          )
          (?:                  # Repeat 0-3 times, separated by a dot
            \.
            (?:
              [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
            |
              0x0*[0-9a-f]{1,2}
            |
              0+[1-3]?[0-7]{0,2}
            )
          ){0,3}                # base ip ends here
          (?:                  # Repeat 0-3 times, separated by a dash
            \-
              (?:
                # Decimal 1-255 (no leading 0's)
                [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
              |
                0x0*[0-9a-f]{1,2}  # Hexadecimal 0x0 - 0xFF (possible leading 0's)
              |
                0+[1-3]?[0-7]{0,2} # Octal 0 - 0377 (possible leading 0's)
              )
              (?:                  # Repeat 0-3 times, separated by a dot
                \.
                (?:
                  [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
                |
                  0x0*[0-9a-f]{1,2}
                |
                  0+[1-3]?[0-7]{0,2}
                )
              ){0,3}
          )
        |
          0x0*[0-9a-f]{1,8}    # Hexadecimal notation, 0x0 - 0xffffffff
        |
          0+[0-3]?[0-7]{0,10}  # Octal notation, 0 - 037777777777
        |
          # Decimal notation, 1-4294967295:
          429496729[0-5]|42949672[0-8]\d|4294967[01]\d\d|429496[0-6]\d{3}|
          42949[0-5]\d{4}|4294[0-8]\d{5}|429[0-3]\d{6}|42[0-8]\d{7}|
          4[01]\d{8}|[1-3]\d{0,9}|[4-9]\d{0,8}
        )
        $
    """, re.VERBOSE | re.IGNORECASE)
    return pattern.match(ip) is not None
 

#
#   This should be significantly fancier... things to improve are:
#       verify that the ips given are on the same network as the hosts' interfaces
#       verify (with netmask) that the range given is valid (are they on the same network?)
#
#       verify that the end address is greater than the base address - done (getting the number of ips does this)
#               if the end address is not greater than the base, the number of addresses would be negative
#       check that there are enough addresses - done
#
#
def checkiprange( answer, min_num_addresses ):  # now includes netmask... 1.2.3.4-22/5
    temp = answer.split("/")
    range = temp[0]
    mask = temp[1]
    if not is_valid_range( range ):
        return False

    if int( mask ) < 0 or int( mask ) > 32:
        return False

    if min_num_addresses != None:
        if iprange_num_ips( range ) < min_num_addresses:
            print( "insufficient number of addresses specified." )
            return False

    return True

def checkwekamem( answer, host ):
    try:
        mb_mem = int( answer )
    except:
        print( "Please enter an integer value of at least " + str(def_ram_per_core) )
        return False

    if mb_mem < def_ram_per_core:
        print( "Please enter an integer value of at least " + str(def_ram_per_core) )
        return False
    
    if mb_mem * host.total_cores > host.usable_mem:
        print( "Not enough memory to supprt " + answer + "MiB per core." )
        return False
    else:
        return True

def list_hosts( hostlist ):
    num_hosts = len(hostlist)
    if num_hosts > 0:
        print( "There are " + str(num_hosts) + " hosts in the current host list:" )
        count = 0
        for host in hostlist:
            print( "\t" +str( count ) + ". " + host.name )
            count += 1

def write_output( arglist ):
    sudoweka = ["sudo" ]
    cmd = sudoweka + arglist
    if outputfile != None:
        try:
            outputfile.write( " ".join( cmd ) )
            outputfile.write( "\n" )
        except:
            return False
    else:
        print( " ".join( cmd ) )
    return True

# returns 0 if successful; 1 if the name resolves, but cannot ping; 2 if cannot resolve
def resolve_name( hostname ):
    #print( "Resolving name " + hostname )
    cmd = ["ping", "-c1", hostname ]
    p = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
    ret = p.wait()
    if ret != 0:
        print( "Bad return code: " + str( ret ) )
        output = p.stderr.read()
        #print( output )
        return ret, ""
    output = str( p.stdout.read(), 'utf-8' )
    #print( output )
    outlist = output.split( "(" )   # "PING us2.sj.lan (172.20.0.2) 56(84) bytes of data." -> ["PING us2.sj.lan", "172.20.0.2) 56(8..."]
    temp = outlist[1]
    templist = temp.split( ")" )    # isolate the ip addr "172.20.0.2) 56(84) bytes of data." -> ["172.20.0.2", " 56(84) bytes of data."]
    ipaddr = templist[0]
    return ret, ipaddr

# See if we can reach the ipaddr/hostname via the interface specified
# returns True/False
def reachable( target, interface = None, host = None ):
    cmd = []
    if host != None:
        cmd.append( "ssh" )
        cmd.append( host )

    cmd.append( "ping" )
    cmd.append( "-c1" )

    if interface != None:
        cmd.append( "-I" )
        cmd.append( interface )

    cmd.append( target )
    #print( cmd )
    p = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
    ret = p.wait()
    if ret != 0:
        return False
    else:
        return True

# returns the ipaddr/mask for the specified interface on a host
def fetch_ip( host, interface ):
    cmd = ["ssh", host, "sudo", "ip", "addr", "show", "dev", interface]

    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True )
    #ret = p.wait()
    tmp = p.stdout.split( "\n" )
    for line in tmp:
        linelist = line.split()
        if linelist[0] == "inet":
            return linelist[1]

    return None

# determine the number of usable cores on a host
def fetch_maxcores( host ):
    # look at the number of cores and check if hyperthreading is on; we can only use 1/2 of the cores with HT on.
    cmd = ["ssh", host, "lscpu"]

    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True )
    tmp = p.stdout.split( "\n" )
    for line in tmp:
        if len( line ) > 0:
            linelist = line.split()
            if linelist[0] == "Thread(s)":
                threads = linelist[3]
            if linelist[0] == "CPU(s):":
                cores = linelist[1]

    return int(cores)/int(threads)

# print( something without a newline )
def announce( text ):
    sys.stdout.flush()
    sys.stdout.write(text)
    sys.stdout.flush()

###################################################################################################################
#
# main()
#


# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("host", help="a hostname; 5 or more are required to create a Weka cluster", nargs='+' )
parser.add_argument("--debug", dest='debug', action='store_true', help="enable debug output")
parser.add_argument("--verbose", dest='verbose', action='store_true', help="enable verbose output")
parser.add_argument("-o", "--outputfile", dest='outputfile', default=None, help="place commands in outputfile as they are executing")
args = parser.parse_args()

if len(args.host) < 5 and not args.debug:
    print( "A minimum of 5 hosts must be specified." )
    sys.exit( 1 )

debug = args.debug


#
# read in the hostnames
#


# Clear the screen
#subprocess.call('clear', shell=True)

print( "Welcome to the WekaIO auto configuration assistant" )
if not args.verbose:
    print(  )
    print( "Analysing hosts..." )

if args.outputfile != None and args.verbose:
    print( "Output will be written to " + args.outputfile )
    print

#print( "hosts are: "  )
#print( args.host )

# create the cluster object
cluster = WekaCluster()         # the target config
serverinfo = WekaCluster()      # the cluster, as seen in STEM mode - base configuration



#if not prompt_yn( "Have you run the server-cert check on all hosts? [Y/n]", "y" ):
#    sys.exit( "Please run the server-cert check on all hosts and try again" )

#print(  )
#if not prompt_yn( "Have you run the deploy script? [Y/n]", "y" ):
#    sys.exit( "Please run the deploy script and try again" )

#
#  Add the hosts to the cluster
#
iperrors = False
if args.verbose:
    print( "Importing hostnames:" )
for hostname in args.host:
    if args.verbose:
        print( "\t" + hostname )
    cluster.hosts[hostname] = WekaHost( hostname )  # add the host to the cluster config (creates the WekaHost object)
    serverinfo.hosts[hostname] = WekaHost( hostname )   # add the host to the source cluster config (creates the WekaHost object)


#
# Start with the details...
#

# Weka should be in STEM mode for all nodes, so we can ask weka what the HW config is...

# fetch the hardware configuration for each host
host_hardware={}
if args.verbose:
    print()
errors = False
for hostname, host in sorted( cluster.hosts.items() ):      # loop through all hosts
    if args.verbose:
        print( "Fetching configuration of host " + hostname + "..." )

    # wil fetch the harware config in JSON
    cmd='weka cluster host info-hw -J -H ' + hostname

    p = subprocess.Popen(cmd, stdout=PIPE, shell=True)
    output = p.stdout.read()

    if len(output) == 0:
        print(f"Unable to fetch config from host {hostname}")
        errors = True
    else:
        # import the JSON
        hardware = json.loads(output)
        host_hardware[hostname]=hardware

if errors:
    print("Error fetching info from hosts.  Please resolve and re-run")
    sys.exit(1)

if args.verbose:
    print( "Hardware information fetch complete." )
if debug:
    print( json.dumps(host_hardware, indent=2, sort_keys=True) )

#
# Fill in hostinfo - our source of information about the cluster & hosts
#   hostinfo is not used for cluster configuration; the actual config will be in "cluster"
#

if args.verbose:
    print()
    print( "Analysing hosts" )
    print()


# version
#for hostname, host in serverinfo.hosts.items():
for hostname, host in cluster.hosts.items():
    hostconfig = host_hardware[hostname]

    keylist = list(hostconfig.keys())
    host.wekaversion = hostconfig[keylist[0]]['version']
    if args.verbose:
        print(f"host {hostname} is version {host.wekaversion}")

# make sure they're all at the same version.  This should never happen, but... ya never know, and it's easy to check
baseversion=None
for hostname, host in cluster.hosts.items():
    if baseversion == None:
        baseversion = host.wekaversion
    else:
        if host.wekaversion != baseversion:
            print("Version mismatch: not all hosts are at the same version. {} != {}".format(baseversion,host.wekaversion))
            print("aborting")
            sys.exit(1)

print()
print(f"Configuring weka cluster version {baseversion}")
print()

# drives
for hostname, host in serverinfo.hosts.items():
    hostconfig = host_hardware[hostname]

    # There should only be one key here - "localhost", but for testing on clusters that are already configured, we'll make sure we use the first one.
    # yes, they all come in as "localhost"
    keylist = list(hostconfig.keys())

    # restructure into a dict so we can sort by name
    disklist = hostconfig[keylist[0]]["disks"]    #this is a list
    diskconfig = {}
    for item in disklist:
        diskconfig[item["devName"]]=item              # build dict with name as key value

    # select which drives are valid
    mountedparts = []
    #for name in sorted( diskconfig.iterkeys() ):
    for name in sorted( diskconfig.keys() ):
        #print( name )
        drive = diskconfig[name]
        drivesize = drive["diskSizeBytes"]/1000/1000/1000
        # what really makes a valid drive?
        if drive["type"] == "PARTITION" and drive["isMounted"] == True:
            mountedparts.append( drive["parentName"] )

    if debug:
        print( "drives with mounted partitions on host " + hostname )
        print( mountedparts )

    # select which drives are valid
    for name in sorted( diskconfig.keys() ):
        drive = diskconfig[name]
        drivesize = drive["diskSizeBytes"]/1000/1000/1000

        if drive["pciAddr"] != "":
            isNvme = True
        else:
            isNvme = False

        # what really makes a valid drive?
        if drive["type"] == "DISK" and drive["isMounted"] == False and drive["devName"] not in mountedparts and isNvme:

            wekadrive = Drive( name, drive["devPath"], drivesize, isNvme )
            host.drives[name] = wekadrive     # drives is a class - valid disk, present to user
            if debug:
                print( wekadrive )

    if debug:
        print( host.drives )

    if len( host.drives ) == 0:         # changed to wekahost from host
        print( "No drives defined for host " + hostname + " - Aborting." )
        sys.exit()

# networks
for hostname, host in serverinfo.hosts.items():
    hostconfig=host_hardware[hostname]

    # name/ip given can be a server mgmt interface, or one of a possible 2 dataplane interfaces
    ret, ipaddr = resolve_name( hostname )      # make sure it's in DNS/hosts file and can ping it
    if ret != 0:
        if ret == 2:
            print( "Unable to resolve hostname " + hostname )
        else:
            print( "Error communicating with host " + hostname  )
        iperrors = True
        sys.exit()          # just bail - there's something wrong in the configuration

    # save the ip address that the hostname resolves to
    host.mgmt_ip = ipaddr
    host.server_mgmt_ip = ipaddr    # new

    # There should only be one key here - "localhost", but for testing on clusters that are already configured, we'll make sure we use the first one.
    keylist= list( hostconfig.keys() )

    # restructure into a dict so we can sort by name
    interfacelist=hostconfig[keylist[0]]["eths"]    #this is a list
    netconfig={}
    for iface in interfacelist:
        netconfig[iface["ethName"]]=iface      # build dict with name as key value

    # look for candidates for the dataplane... try to figure out the topology here
    for name in sorted( netconfig.keys() ):
        interface=netconfig[name]
        # only note valid interfaces - ignore others.
        # this may include the server management interface (if it's jumbo frame), so we have to be mindful of that...
        if interface["mtu"] > 4000 and interface["ip4"] != "" and interface["validationCode"] == "OK" and interface["linkDetected"] == True:
            if_obj = IPInterface( name, interface["linkLayer"], interface["ip4"], interface["mtu"], interface["device"], interface["speedMbps"] )      # create object
            host.ipifs[name] = if_obj

    if len( host.ipifs ) == 0:
        print( "No network interfaces defined for host " + hostname + " - Aborting." )
        sys.exit()

# cores
#   need to rework this due to newer memory allocation scheme
if args.verbose:
    print()
    print( "Analysing core configuration" )
    print()
for hostname, host in serverinfo.hosts.items():
    hostconfig = host_hardware[hostname]
    # There should only be one key here - "localhost", but for testing on clusters that are already configured, we'll make sure we use the first one.
    keylist=list(hostconfig.keys())

    host.total_cores = fetch_maxcores( hostname )   # check the servers and get the max number of cores
    host.usable_cores = host.total_cores - 1       # leave 1 core for the OS
    if host.usable_cores > max_cores:   # max is 19
        host.usable_cores = max_cores

    #print( keylist )
    memdict = hostconfig[keylist[0]]["memory"]

    host.memory = memdict["total"]/1024/1024  # make it in MiB
    host.usable_mem = host.memory - 16384 - 5120   # leave 16GiB for the OS, deduct another 5GiB for Weka

    max_ram_per_core = host.usable_mem / host.usable_cores

    if max_ram_per_core < def_ram_per_core:               # min 1.4GiB per core by default; 7.5GiB preferred
        host.usable_cores = host.usable_mem / def_ram_per_core
    
    if max_ram_per_core < 7680:               # 7.5GB per core is preferred/max?
        host.bp_cores = host.usable_mem / 7680
        if host.bp_cores > max_cores:   # max is 19
            host.bp_cores = max_cores
        if host.bp_cores > host.usable_cores:
            host.bp_cores = host.usable_cores
    else:
        host.bp_cores = host.usable_cores

    if args.verbose:
        print( "Host " + hostname + " has " + str( host.total_cores ) + " total cores," + str( host.usable_cores ) + " weka usable cores, and " + str(host.bp_cores) + " Best Practice cores" )

if args.verbose:
    print()

###################################################################################################################
#
# we're done with host_hardware
#
del host_hardware

#
# Take a look at a random host (the last one, actually) to see if we're running in aws
#
if hostconfig[keylist[0]]["aws"]["availabilityZone"] != "":  # is an AZ set?  If so, we're not on-prem!
    cluster.aws = True


#
# let's take a peek...  if all the hosts are identical, we can make some assumptions and reduce the numbers of questions we have to ask...
#
is_identical = True     # assume true until proven false

# pick the first host, use it as a reference to see if all the hosts look the same as it does.
reference_host = list(serverinfo.hosts.values())[0]            # actually now a dict

# loop through all hosts and look for anything different from the reference host
for hostname, host in serverinfo.hosts.items():
    # the easy stuff - same cores & memory?  Number of ip interfaces and drives?

    if ((reference_host.total_cores != host.total_cores) or (reference_host.usable_cores != host.usable_cores) or 
            (int(reference_host.memory/100) != int(host.memory/100)) or 
            (int(reference_host.usable_mem/100) != int(host.usable_mem/100)) or 
            (len( reference_host.ipifs ) != len( host.ipifs )) or (len( reference_host.drives ) != len( host.drives ))):
        is_identical = False
        print( "There appears to be a mismatch between this host and the Reference Host:" )
        print( "Hostname " + host.name + "(ref=" + reference_host.name + ")" )
        print( "Host Memory = " + str( host.memory ) + "/" + str( reference_host.memory ) )
        print( "Host Usable Memory = " + str( host.usable_mem ) + "/" + str( reference_host.usable_mem ) )
        print( "Host total cores = " + str( host.total_cores ) + "/" + str( reference_host.total_cores ) )
        print( "Usable cores = " + str( host.usable_cores ) + "/" + str( reference_host.usable_cores ) )
        print( "IPS = " + str( len( host.ipifs ) ) + "/" + str( len( reference_host.ipifs ) ) )
        print( "Drives = " + str( len( host.drives ) ) + "/" + str( len( reference_host.drives ) ) )
        print()
        print( "All hosts need to be identical" )
        print( "Please check your configuration and try again" )

    # check if all ip interfaces are the same
    for interface in host.ipifs:
        if interface not in reference_host.ipifs:
            is_identical = False
        # ok, it's present, but is it the SAME?
        # this should print( out anything that's different. )
        if host.ipifs[interface].ifname != reference_host.ipifs[interface].ifname:  #is that even possible?
            is_identical = False
        elif host.ipifs[interface].linklayer != reference_host.ipifs[interface].linklayer:
            is_identical = False
        elif host.ipifs[interface].mtu != reference_host.ipifs[interface].mtu:
            is_identical = False
        elif host.ipifs[interface].gateway != reference_host.ipifs[interface].gateway:
            is_identical = False
        elif host.ipifs[interface].netmask != reference_host.ipifs[interface].netmask:
            is_identical = False
        elif host.ipifs[interface].network != reference_host.ipifs[interface].network:
            is_identical = False
        elif host.ipifs[interface].speed != reference_host.ipifs[interface].speed:
            is_identical = False
    
    # check if all drives are the same
    for drive in host.drives:
        if drive not in reference_host.drives:
            is_identical = False

# are the above tests sufficient to determine if they're identical?
#  possible additions - verify drive sizes are same, network topologies are same, etc

homogenous = False
if is_identical:
    homogenous = True
    if args.verbose:
        print( "Configuring homogenous cluster" )
else:
    print( "Cluster hosts do not appear to be homogenous.  Aborting auto-config" )
    sys.exit( 1 )


#
# dedicated hosts?  - auto-config - always true
#
if args.verbose:
    print()
cluster.isdedicated = True


###################################################################################################################
#
# Drive selection
#
if args.verbose:
    print()
    print( "Drive Selection:" )
    print()
# select drives for Weka
reference_host = None
for hostname, host in sorted( cluster.hosts.items() ):
    if args.verbose:
        print( "Drives for host " + hostname + ":" )
    if reference_host != None:
        for name, drive in sorted( reference_host.drives.items() ):        # is a dict of name:Drive obj
            host.drives[name]=drive                        # change to object
            if args.verbose:
                print( "added " + name )
    else:
        for name, drive in sorted( serverinfo.hosts[hostname].drives.items() ): # loop through drives from source config
            #if drive.isNvme:
            #    prompt_str = name + "(NVMe): " + drive.path + ", " + str(drive.size) + "GB [Y/n]"
        #else:
            # not supporting sata drives anymore
    #    prompt_str = name + "(SAS/SATA): " + drive.path + ", " + str(drive.size) + "GB [Y/n]"

            #if prompt_yn( prompt_str, "y" ):
            if drive.isNvme:
                host.drives[name]=drive

        if len( host.drives ) == 0:
            print( "No drives defined for host " + hostname + " - Aborting." )
            sys.exit()

        if homogenous:
            reference_host = host

# copy over management network
for hostname, host in sorted( cluster.hosts.items() ):
    # copy over the ip address that this hostname resolves to - we'll start with that as the weka mangement ip
    host.mgmt_ip = serverinfo.hosts[hostname].mgmt_ip       # we may need to change this to the dataplane network
    host.server_mgmt_ip = serverinfo.hosts[hostname].server_mgmt_ip       # this may be the same as the dataplane network

###################################################################################################################
#
# Dataplane Network selection
#
if args.verbose:
    print()
    print( "Dataplane Network Interfaces:" )
    print()

if args.verbose:
    print()
reference_host = None
for hostname, host in sorted( cluster.hosts.items() ):
    if args.verbose:
        print( "Dataplane Network Interfaces for host " + hostname + ":" )
    if reference_host != None:
        for name, ipobj in sorted( reference_host.ipifs.items() ):
            ipobj = serverinfo.hosts[hostname].ipifs[name]        # pull ipobj from serverinfo, not reference_host so it has correct ip addr

            host.ipifs[name] = ipobj    # ! ipobj needs to come from serverinfo so we have the correct ip addr!
            #if ipobj.maxVirtFunctions > 0:
            #    host.total_vfs += ipobj.maxVirtFunctions
            #    host.num_vf_interfaces += 1

            # get netmask from host - do this here, so we only do interfaces that are being configured/used.
            ip_info = fetch_ip( hostname, name )
            if ip_info != None:
                ipobj.netmask = int( ip_info.split( '/' )[1] )  # split() produces a list, and we want the second item
                ipobj.network = network_ip( ipobj.ipaddr, ipobj.netmask )
            else:
                print( "Error getting netmask for interface " + name + " from host " + hostname )

            if args.verbose:
                print( "added " + name + ", ip addr " + ipobj.ipaddr + ", mtu " + str(ipobj.mtu) )
    else:

        for name, ipobj in sorted( serverinfo.hosts[hostname].ipifs.items() ):
            # don't even show interfaces that aren't relevant
            host.ipifs[name] = ipobj

            # get netmask from host - do this here, so we only do interfaces that are being configured/used.
            ip_info = fetch_ip( hostname, name )
            if ip_info != None:
                ipobj.netmask = int( ip_info.split( '/' )[1] )  # split() produces a list, and we want the second item
                ipobj.network = network_ip( ipobj.ipaddr, ipobj.netmask )
            else:
                print( "Error getting netmask for interface " + name + " from host " + hostname )

        if len( host.ipifs ) == 0:
            print( "No network interfaces defined for host " + hostname + " - Aborting." )
            sys.exit()

        if homogenous:
            reference_host = host


#
# Default-net - clusterwide setting
#
# This needs more testing
setdefnet = False

###################################################################################################################
#
# Cores selection
#
if args.verbose:
    print()
    print( "Cores Selection:" )
    print()

# check if all hosts have the same number of cores?  Does it matter?
# prompt number of FE cores, SSD cores, etc.
# Total cores = # ip interfaces?   On AWS, yes.  On-prem, no... we'll create what we need - start with 1 IP per interface.
# Figure the max cores - max_cores = server total cores - 2?; max of 19.
reference_host = None
for hostname, host in sorted( cluster.hosts.items() ):
    if args.verbose:
        print( "Cores selection for host " + hostname + ":" )
    if reference_host != None:
        host.drives_cores = reference_host.drives_cores
        host.total_cores =  reference_host.total_cores
        host.usable_cores = reference_host.usable_cores
        host.bp_cores = reference_host.bp_cores
        host.memory = reference_host.memory
        host.usable_mem = reference_host.usable_mem
        host.total_cores = reference_host.total_cores
        host.fe_cores = reference_host.fe_cores
        host.weka_memory = reference_host.weka_memory

        if args.verbose:
            print( "cores set" )
    else:
        host.total_cores = serverinfo.hosts[hostname].total_cores
        host.usable_cores = serverinfo.hosts[hostname].usable_cores
        host.bp_cores = serverinfo.hosts[hostname].bp_cores

        host.memory = serverinfo.hosts[hostname].memory
        host.usable_mem = serverinfo.hosts[hostname].usable_mem

        max_ram_per_core = host.usable_mem / host.usable_cores

        host.total_cores = host.usable_cores    # use them all!

        # special case for aws i3.xlarge instances, which have only 1 core available
        if host.total_cores == 1:
            default_cores = 0
        else:
            default_cores = 1
        host.fe_cores = default_cores

        # no more than 1 core per drive
        max_drive_cores = len( host.drives )

        # Figure optimal number of drive cores vs compute cores
        if max_drive_cores <= (host.usable_cores - host.fe_cores)/2:   # have at least as many compute cores as drive cores
            optimal_drive_cores = int(max_drive_cores)
        else:
            optimal_drive_cores = int((max_drive_cores+1)/2)     # 2 drives per core, but what about an odd number of drives? (add 1 to round up)

        # special case for aws i3.xlarge instances, which have only 1 core available
        if host.total_cores == 1:
            optimal_drive_cores = 0
        
        if args.verbose:
            print( "Optimal drive cores is " + str( optimal_drive_cores ) + ".  There are " + str( len( host.drives ) ) + " drives on this host" )
        host.drives_cores = optimal_drive_cores

        #if homogenous:
        reference_host = host

if args.verbose:
    print()

###################################################################################################################
#
# Check if all the DataPlane interfaces are on the same network
#

#  dict of {network: [host...]}

# take some notes... sort hosts by network
#clusternets = {}    # dict of {network:[hosts...]}  - a list of hosts on a network segment  (do I really need this?  should be all:all, no?)  maybe we should verify that they are all:all?
#clusternet_ips = {}    # dict of {network:[hosts...]} - a list of ips on a network segment
#for hostname, host in sorted( cluster.hosts.items() ):
#    for name, ipobj in sorted( host.ipifs.items() ):
#        #net_list = clusternets.get( ipobj.network )
#        #if net_list == None:
#        if ipobj.network not in clusternets:
#            clusternets[ipobj.network] = [host]
#            clusternet_ips[ipobj.network] = [ipobj.ipaddr]
#        else:
#            clusternets[ipobj.network].append( host )
#            clusternet_ips[ipobj.network].append(ipobj.ipaddr)
#
#print(f"clusternets={clusternets}")


# new style to get gateways
for hostname, host in sorted(cluster.hosts.items()):
    for ifname, ipobj in sorted(host.ipifs.items()):    # for each ip interface...
        # see if there is a gateway, and if so, record it
        cmd = ["ssh", host.name, "sudo", "ip", "route", "get", "8.8.8.8", "oif", ifname]

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ret = p.wait()
        for line in p.stdout:
            linelist = line.split()
            if linelist[0] == "8.8.8.8" and linelist[1] == "via":
                ipobj.gateway = linelist[2]
                print(f"gateway found for iface {ifname}: {ipobj.gateway}")
                break       # move on to next interface
                #continue


#
# determine what the gateways are if we have more than one network in the cluster
#
#if len(clusternets) > 1:
#    # select a target ip for each network - this is some funky logic
#    targets = {}    # dict of {network:target_ip}, where target_ip is an ip NOT on that network
#    for network, hostlist in clusternets.items():                   # go through the list of networks
#        for host in hostlist:   # loop through the hosts on the network
#            for name, ipobj in sorted( host.ipifs.items() ): # loop through that hosts's ip interfaces
#                if ipobj.network == network:    # is it on the network we're looking at?
#
#
#
        #for target_network, target_hostlist in clusternets.items(): # go through again, find a different network
        #    print(f"{network}-{target_network}")
        #    if network != target_network:
        #        ipname=next(iter(target_hostlist[0].ipifs))                     # take the first host's first ip addr on that network
        #        targets[network] = target_hostlist[0].ipifs[ipname].ipaddr      # take the first host's first ip addr on that network
        #        break                                                       # move on to next network 

#    print(targets)
#    gateways = {}   # dict of {network:gateway}
#    for network, hostlist in clusternets.items():                   # go through the list of networks
#        for host in hostlist:
#            target_ip = targets[network]                            # get the target for this host
#            # ip route get "target" returns "172.172.2.3 via 172.172.1.1 dev ens2 src 172.172.1.200"
#            # which is 'target "via" gateway "dev" interface "src" source_ip
#            cmd = ["ssh", host.name, "sudo", "ip", "route", "get", target_ip]
#
#            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#            ret = p.wait()
#            for line in p.stdout:
#                linelist = line.split()
#                if linelist[0] == target_ip and linelist[1] == "via":
#                    gateways[network] = linelist[2]
#                    break                   # all hosts on the same network should have the same gateway (not in GPG networks!)
#            
#            if gateways.get( network ) != None:     # make sure we got one, if not try another host (host misconfigured?)
#                break                               # if so, no need to look at other hosts on this network
#
#    print(gateways)
#    # go make notes on all the hosts' interfaces
#    for hostname, host in sorted( cluster.hosts.items() ):
#        for name, ipobj in sorted( host.ipifs.items() ):
#            print(f"{hostname}/{name}")
#            ipobj.gateway = gateways[ipobj.network]



# get the ip address range

if args.verbose:
    print()


#
# We're done with serverinfo... go ahead and delete it
#
del serverinfo


###################################################################################################################
#
# Management Network selection
#

#  IB is never routable to 
#if cluster.isIB:
#    cluster.dataplane_mgmt = True
cluster.isIB=False
cluster.dataplane_mgmt = True

if args.verbose:
    print()
    print( "Verifying mangement network connectivity:" )
    print()
#
#   in order to use the hostnames in the input file as weka management interfaces, the dataplane
#       must be able to route to it.
#

# so, we've determined that all hosts have the same exact network interfaces (only difference being ip addr).
# we can use this assumption to simplfy things...

# are ANY of the interfaces IB?  If so, assume IB dataplane
#for hostname, host in sorted( cluster.hosts.items() ):
#    #for name, ipobj in sorted( cluster.hosts[hostname].ipifs.iteritems() ):
#    for name, ipobj in sorted( host.ipifs.items() ): # check them all
#        if ipobj.linklayer == "IB": 
#            cluster.isIB=True

# forget ETH interfaces if it's an IB cluster - they can't be dataplane and we want only dp interfaces
#if cluster.isIB == True:
#    for hostname, host in sorted( cluster.hosts.items() ):
#        for name, ipobj in sorted( host.ipifs.items() ):
#            if ipobj.linklayer == "ETH":
#                del host.ipifs[name]

# with what's left, what are our weka management interfaces?
for hostname, host in sorted( cluster.hosts.items() ):

    # adjust for new weka versions allowing more than 2 ip interfaces
    temp = host.wekaversion.split('.')
    #print(f"host.wekaversion={host.wekaversion}")
    major = int(temp[0])
    minor = int(temp[1])
    if major >= 3 and minor >= 10:
        max_ip_interfaces = 8
    else:
        max_ip_interfaces = 2

    for name, ipobj in sorted( host.ipifs.items() ):
        host.mgmt_ip = ipobj.ipaddr     
        host.weka_mgmt_ip.append( ipobj.ipaddr )
    # ok, so we're going to punt if we can't figure it out - hopefully this is a rare occurance
    if len( host.weka_mgmt_ip ) > max_ip_interfaces:
        print( "Error: host " + hostname + " has more than "+ str(max_ip_interfaces)+" possible dataplane interfaces." )
        print( " Manual configuration required." )
        sys.exit(1)

#
# Gather the rest of the info we need to create the cluster
#

# Have them name the cluster
print()
default_ans=cluster.name
name = prompt( "Enter a name for this new cluster", default_ans, "Invalid name: please enter a string of aphpanumeric characters", checkname, None )
cluster.name = name 

#
# support cloud enabled?
#
print()
if cluster.cloudenable:
    default_ans="Y"
else:
    default_ans="N"

cluster.cloudenable = prompt_yn( "Do you want to enable Cloud monitoring? [Y/n]", default_ans )

###################################################################################################################
#
# Coding scheme
#
if args.verbose:
    print()
    print( "Stripe Width:" )
num_hosts=len(cluster.hosts) 

# handle the special case of 6 hosts separately, so it's clear what we're doing
if num_hosts == 5 or num_hosts == 6 :      # special case - this is the only case where we support 1 spare (6-node clusters)
    cluster.parity = 2
    cluster.data = 3
    if args.verbose:
        print( "Cluster size is 6; forcing 3+2 Stripe Width" )
else:

    num_parity = 2
    cluster.parity = num_parity


    # make sure they have at least 2 spares
    max_drives = num_hosts - num_parity
    if max_drives > 16:
        max_drives = 16

    if max_drives < 3:
        max_drives = 3  #shouldn't this be an error?  this should be unreachable


    cluster.data = max_drives

###################################################################################################################
#
# Hot Spares
#
if args.verbose:
    print()
    print( "Hot Spares:" )

cluster.hot_spares = 1


###################################################################################################################
#
# We now have all the info needed to create the cluster
#
###################################################################################################################

print()
print( "Generating output" )
print()

if args.outputfile != None:
    outputfile = open( args.outputfile, "w" )
else:
    outputfile = None

cmd = [ "weka", "cluster", "create" ] 
for hostname, host in sorted( cluster.hosts.items() ):
    cmd.append( hostname )

# do we need to add "--host-ips=" ?
hostips = "--host-ips="

for hostname, host in sorted( cluster.hosts.items() ):
    if len( host.weka_mgmt_ip ) < 2:
        thishost_ips =  host.weka_mgmt_ip[0]
    else:
        thishost_ips = None
        for ip in host.weka_mgmt_ip:
            if thishost_ips == None:
                thishost_ips = ip
            else:
                thishost_ips += '+' + ip
        #thishost_ips = host.weka_mgmt_ip[0] + "+" + host.weka_mgmt_ip[1]    # HA config
    hostips = hostips + thishost_ips + ","
# remove trailing "," and add it to the command
cmd.append( hostips[:-1] )

if not write_output( cmd ):
    sys.exit( "I/O error on output" )

if not write_output( ["sleep", "10"] ):
    sys.exit( "I/O error on output" )

host_hostids={}
hostid=0
for hostname, host in sorted( cluster.hosts.items() ):
    host_hostids[hostname] = hostid
    hostid += 1

# map it in
for hostname, host in sorted( cluster.hosts.items() ):
    host.hostid = int( host_hostids[hostname] )
    if args.verbose:
        print( "# Expected hostid - " + hostname + " = " + str( host.hostid ) )

cmd=["weka", "cluster", "update", "--cluster-name=" + cluster.name] 
if not write_output( cmd ):
    sys.exit( "I/O error on output" )

#
# add network interfaces
#

for hostname, host in sorted( cluster.hosts.items() ):
    for interface, ipobj in sorted( host.ipifs.items() ):
        #if host.num_vf_interfaces == 0 and ipobj.ipaddr == host.mgmt_ip:     # only aws instances don't have vf interfaces!
        #    continue                                                        # don't give the management interface to the dataplane
        cmd=["weka", "cluster","host", "net", "add", str(host.hostid), interface]
        if ipobj.netmask != None:
            cmd.append( "--netmask=" + str(ipobj.netmask) )

        if ipobj.gateway != None:
            cmd.append( "--gateway=" + ipobj.gateway )

        # occasionally, some hosts aren't ready for this yet, so retry it a few times
        if not write_output( cmd ):
            sys.exit( "I/O error on output" )


#
# add drives
#
for hostname, host in sorted( cluster.hosts.items() ):
    #cmd = ["weka", "cluster", "drive", "add", str(host.hostid), drive.path, "--force"]
    cmd = ["weka", "cluster", "drive", "add", str(host.hostid)]
    for drive, drive in sorted( cluster.hosts[hostname].drives.items() ): # loop through drives 
        cmd.append(drive.path)
    cmd.append("--force")

    if not write_output( cmd ):
        sys.exit( "I/O error on output" )

#
# configure cores
#
for hostname, host in sorted( cluster.hosts.items() ):
    cmd = [ "weka", "cluster", "host", "cores", str(host.hostid), str(host.total_cores) ]
    if host.fe_cores > 0:
        cmd.append( "--frontend-dedicated-cores" )
        cmd.append( str(host.fe_cores) )
    if host.drives_cores > 0:
        cmd.append( "--drives-dedicated-cores" )
        cmd.append( str(host.drives_cores) )

    if not write_output( cmd ):
        sys.exit( "I/O error on output" )

# no longer needed
# weka cluster drive scan
#cmd = ["weka", "cluster", "drive", "scan"]
#if not write_output( cmd ):
#    sys.exit( "I/O error on output" )
#
#if not write_output( ["sleep", "60"] ):
#    sys.exit( "I/O error on output" )


if cluster.isdedicated:
    for hostname, host in sorted( cluster.hosts.items() ):
        cmd = ["weka", "cluster", "host", "dedicate", str(host.hostid), "on"]
        if not write_output( cmd ):
            sys.exit( "I/O error on output" )
else:
    for hostname, host in sorted( cluster.hosts.items() ):
        if host.weka_memory != 0:           # 0 is the default, un-set value
            print( "Setting host " + hostname + " memory setting" )
            # Setting is in bytes.  How sad.
            cmd = ["weka", "cluster", "host", "memory", str(host.hostid), str(host.weka_memory * host.total_cores * 1024 * 1024)]
            if not write_output( cmd ):
                sys.exit( "I/O error on output" )
    
#weka cloud enable
if cluster.cloudenable:
    cmd = ["weka", "cloud", "enable"]
    if not write_output( cmd ):
        sys.exit( "I/O error on output" )



#weka cluster update [--data-drives=<num>] [--parity-drives=<num>]
cmd = ["weka", "cluster", "update", "--data-drives=" + str(cluster.data), "--parity-drives=" + str(cluster.parity)]
if not write_output( cmd ):
    sys.exit( "I/O error on output" )

#weka cluster hot-spare <count>
if cluster.hot_spares > 0:
    # hot-spares require failure-domains 
    for hostname, host in sorted( cluster.hosts.items() ):
        cmd = ["weka", "cluster", "host", "failure-domain", str(host.hostid), "--auto"]
        if not write_output( cmd ):
            sys.exit( "I/O error on output" )

    cmd = ["weka", "cluster", "hot-spare", str( cluster.hot_spares )]
    if not write_output( cmd ):
        sys.exit( "I/O error on output" )



# weka cluster host apply
cmd = ["weka", "cluster", "host", "apply", "--all", "--force" ]
if not write_output( cmd ):
    sys.exit( "I/O error on output" )

if not write_output( ["sleep", "60"] ):
    sys.exit( "I/O error on output" )

# no longer needed
# weka cluster drive activate
#cmd = ["weka", "cluster", "drive", "activate"]
#if not write_output( cmd ):
#    sys.exit( "I/O error on output" )

#weka cluster start-io
cmd = ["weka", "cluster", "start-io"]
if not write_output( cmd ):
    sys.exit( "I/O error on output" )

if outputfile != None:
    outputfile.close()

print( "Process complete." )

#  All done!
