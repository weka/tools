#!/usr/bin/env python3

#from __future__ import absolute_import
import json
import argparse
import glob
#from plumbum import SshMachine, colors
import sys
import logging
import traceback
import os
import threading
import time
from contextlib import contextmanager


"""A Python context to move in and out of directories"""
@contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)

# print( something without a newline )
def announce( text ):
    sys.stdout.flush()
    sys.stdout.write(text)
    sys.stdout.flush()

# finds a string variable in the script, such as DESCRIPTION="this is a description"
def find_value( script, name ):
    desc_start = script.find( name )
    if desc_start != -1:
        desc_begin = script.find( '"', desc_start ) + 1
        desc_end = script.find( '"', desc_begin )
        #desc = "(" + server + ") " + script[desc_begin:desc_end] 
        #return( desc.ljust(70) )
        desc = script[desc_begin:desc_end] 
        return( desc )
    else:
        return( "ERROR: Script lacks variable declaration for " + name )

def remote_exec( server, conn, scriptname, cmd ):
    stdout_txt=""
    stderr_txt=""

    # use our own version of plumbum - Ubuntu is broken. (one line change from orig plumbum... /bin/sh changed to /bin/bash
    sys.path.insert( 1, os.getcwd() + "/plumbum-1.6.8" )
    from plumbum import SshMachine, colors

    s = conn.session()
    retcode, stdout_txt, stderr_txt = s.run( cmd, retcode=None )
    command_results=[retcode,stdout_txt]     # save our results
    return retcode,command_results

thread_results={}
def thread_exec( server, conn, scriptname, cmd ):
    global thread_results
    retcode,command_results = remote_exec( server, conn, scriptname, cmd )
    if not scriptname in thread_results:
        thread_results[scriptname]={}
    thread_results[scriptname][server] = command_results

# pass server name/ip, ssh session, and list of scripts
def run_scripts( servers, ssh_sessions, scripts, args, preamble ):      
    scriptresults = {}
    num_warn=0
    num_fail=0
    num_pass=0

    # use our own version of plumbum - Ubuntu is broken. (one line change from orig plumbum... /bin/sh changed to /bin/bash
    sys.path.insert( 1, os.getcwd() + "/plumbum-1.6.8" )
    from plumbum import colors

    # execute each script
    for scriptname in scripts:
        max_retcode = 0
        f = open( scriptname )  # open each of the scripts
        if f.mode == "r":
            script = f.read()  # suck the contents of the script file into "script"
        else:
            script=""   # open failed
            announce( "\nUnable to open " + scriptname + "\n" )
            continue

        #if args.verbose_flag:      # oops... not in there...  have to think on how to note verbosity
        #    announce( "\nExecuting script " + scriptname + " on server " + server + ":\n" )

        # saw that script we're going to run:
        announce( find_value( script, "DESCRIPTION" ).ljust(70) )

        script_type = find_value( script, "SCRIPT_TYPE" )    # should be "single", "parallel", or "sequential"
        #announce( "\n" )
        #announce( "\ndebug: script type is '" + script_type + "'\n" )
        #announce( "\n" )

        command="( eval set -- " + args + "\n" + preamble + script + ")"

        if script_type == "single":

            server = servers[0]
            # run on a single server - doesn't matter which
            retcode,result = remote_exec( server, ssh_sessions[server], scriptname, command )
            if not scriptname in results:
                results[scriptname] = {}
            results[scriptname][server] = result
            max_retcode = retcode

        elif script_type == "sequential":
            for server in servers:
                # run on all servers, but one at a time (sequentially)
                retcode,result = remote_exec( server, ssh_sessions[server], scriptname, command )
                if not scriptname in results:
                    results[scriptname] = {}
                results[scriptname][server] = result

                # note if any failed/warned.
                if retcode > max_retcode:
                    max_retcode = retcode

        elif script_type == "parallel":
            # run on all servers in parallel
            # spawn a thread for each remote_exec() call so they run in parallel, then wait for them.
            global thread_results
            parallel_threads={}

            # create and start the threads
            for server in servers:
                parallel_threads[server] = threading.Thread( target=thread_exec, args=(server, ssh_sessions[server], scriptname, command ) )
                parallel_threads[server].start()

            # wait for and reap threads
            time.sleep( 0.1 )
            #print( "parallel_threads = " + str( len( parallel_threads ) ) )
            while len( parallel_threads ) > 0:
                #print( "parallel_threads = " + str( len( parallel_threads ) ) )
                dead_threads = {}
                for server, thread in parallel_threads.items():
                    if not thread.is_alive():   # is it dead?
                        #print( "    Thread on " + server + " is dead, reaping" )
                        thread.join()       # reap it
                        dead_threads[server] = thread

                #print( "dead_threads = " + str( dead_threads ) )
                # remove it from the list so we don't try to reap it twice
                for server, thread in dead_threads.items():
                    #print( "    removing " + server + "'s thread from list" )
                    parallel_threads.pop( server )

                # sleep a little so we limit cpu use
                time.sleep( 0.1 )

            #time.sleep( 2.0 )
            # all threads complete - check return codes
            #    thread_results[scriptname][server] = command_results
            #print( "thread_results is: ") 
            #print( json.dumps(thread_results, indent=4, sort_keys=True) )
            #result_list=[]
            for server, result_list in thread_results[scriptname].items():
                if result_list[0] > max_retcode:
                    max_retcode = result_list[0]

            if not scriptname in results:
                results[scriptname] = {}

            results.update( thread_results )
            thread_results={}

        else:
            announce( "\nERROR: Script failure: SCRIPT_TYPE in script " + scriptname + " not set.\n" )
            print( "HARD FAIL - terminating tests.  Please resolve the issue and re-run." )
            sys.exit( 1 )


        # end of the if statment - check the return codes
        if max_retcode == 0:                # all ok
            print( "\t[", colors.green | "PASS", "]"  )
            num_pass += 1
        elif max_retcode == 255:            # HARD fail, cannot continue
            print( "\t[", colors.red | "HARDFAIL", "]"  )
        elif max_retcode == 254:            # warning
            print( "\t[", colors.yellow | "WARN", "]"  )
            num_warn += 1
        else:                           # minor fail
            print( "\t[", colors.red | "FAIL", "]"  )
            num_fail += 1
            

        #if args.verbose_flag or retcode != 0:
        #if retcode != 0:
        #    print( "script returned:" )
        #    print( stdout_txt )
        #    print( stderr_txt )
        #    print( "==================================================" )

        if max_retcode == 255:
            print( "HARD FAIL - terminating tests.  Please resolve the issue and re-run." )
            # return early
            return num_pass,num_warn,num_fail,results
            #sys.exit( 1 )

    return num_pass,num_warn,num_fail,results

ssh_sessions={}
def open_ssh_connection( server ):
    global ssh_sessions
    try:
        sys.path.insert( 1, os.getcwd() + "/plumbum-1.6.8" )
        from plumbum import SshMachine, colors
        connection = SshMachine( server )  # open an ssh session
        s = connection.session()
        ssh_sessions[server] = connection      # save the sessions
    except:
        traceback.print_exc(file=sys.stdout)
        print( "Error ssh'ing to server " + server )
        print( "Passwordless ssh not configured properly, exiting" )
        ssh_sessions[server] = None
        return -1

#
#   main
#

# parse arguments
progname=sys.argv[0]
parser = argparse.ArgumentParser(description='Execute server cert scripts on servers')
parser.add_argument('servers', metavar='servername', type=str, nargs='+',
                    help='Server Dataplane IPs to execute on')
#parser.add_argument("-d", "--scriptdir", dest='scriptdir', default="etc/cluster.d", help="Directory of files to execute, typically ./etc/cluster.d")
parser.add_argument("-c", "--clusterscripts", dest='clusterscripts', action='store_true', help="Execute cluster-wide scripts")
parser.add_argument("-s", "--serverscripts", dest='serverscripts', action='store_true', help="Execute server-specific scripts")
parser.add_argument("-p", "--perfscripts", dest='perfscripts', action='store_true', help="Execute performance scripts")

# these next args are passed to the script and parsed in etc/preamble - this is more for syntax checking
#parser.add_argument("-v", "--verbose", dest='verbose_flag', action='store_true', help="enable verbose mode")
parser.add_argument("-j", "--json", dest='json_flag', action='store_true', help="enable json output mode")
parser.add_argument("-f", "--fix", dest='fix_flag', action='store_true', help="don't just report, but fix any errors if possible")

args = parser.parse_args()

with pushd( os.path.dirname( progname ) ):
    # make sure passwordless ssh works to all the servers because nothing will work if not set up
    announce( "Opening ssh sessions to all servers\n" )
    parallel_threads={}
    for server in args.servers:
        # create and start the threads
        parallel_threads[server] = threading.Thread( target=open_ssh_connection, args=(server,) )
        parallel_threads[server].start()

    # wait for and reap threads
    time.sleep( 0.1 )
    #print( "parallel_threads = " + str( len( parallel_threads ) ) )
    while len( parallel_threads ) > 0:
        #print( "parallel_threads = " + str( len( parallel_threads ) ) )
        dead_threads = {}
        for server, thread in parallel_threads.items():
            if not thread.is_alive():   # is it dead?
                #print( "    Thread on " + server + " is dead, reaping" )
                thread.join()       # reap it
                dead_threads[server] = thread

        #print( "dead_threads = " + str( dead_threads ) )
        # remove it from the list so we don't try to reap it twice
        for server, thread in dead_threads.items():
            #print( "    removing " + server + "'s thread from list" )
            parallel_threads.pop( server )

        # sleep a little so we limit cpu use
        time.sleep( 0.1 )

        #ret = open_ssh_connection( server )
        #if ret == -1:
        #    sys.exit( 1 )

    #print( ssh_sessions )
    if len( ssh_sessions ) == 0:
        print( "Error opening ssh sessions" )
        sys.exit( 1 )
    for server, session in ssh_sessions.items():
        if session == None:
            print( "Error opening ssh session to " + server )

    announce( "\n" )

    # ok, we're good... let's go
    results={}

    # get the list of scripts in ./etc/server.d or ./etc/cluster.d, depending on the arguments - hard code for cluster certification?
    if not args.clusterscripts and not args.serverscripts and not args.perfscripts:
       # unspecicified by user so execute all scripts
        scripts = [f for f in glob.glob( "./scripts.d/[0-9]*")]
    else:
        scripts=[]
        if args.clusterscripts:
            scripts += [f for f in glob.glob( "./scripts.d/0*")]
        if args.serverscripts:
            scripts += [f for f in glob.glob( "./scripts.d/[1-2]*")]
        if args.perfscripts:
            scripts += [f for f in glob.glob( "./scripts.d/5*")]


    # sort them so they execute in the correct order
    scripts.sort()

    # get the preamble file - commands and settings for all scripts
    preamblefile = open( "./scripts.d/preamble" )
    if preamblefile.mode == "r":
        preamble = preamblefile.read() # suck in the contents of the preamble file
    else:
        preamble="" # open failed

    # save the server names/ips to pass to the subscripts
    arguments=""

    #if args.verbose_flag:
    #    arguments = arguments + "-v "

    if args.json_flag:
        arguments = arguments + "-j "

    if args.fix_flag:
        arguments = arguments + "-f "

    for server in args.servers:
        arguments += server + ' '


    cluster_results={}
    num_passed=0
    num_failed=0
    num_warned=0


    results={}

    num_passed,num_warned,num_failed,results = run_scripts( args.servers, ssh_sessions, scripts, arguments, preamble )

    if args.json_flag:
        print( json.dumps(results, indent=2, sort_keys=True) )

    print( )
    print( "RESULTS: " + str( num_passed ) + " Tests Passed, " + str( num_failed ) + " Failed, " + str( num_warned ) + " Warnings"  )
    #print( json.dumps(cluster_results, indent=2, sort_keys=True) )

    fp = open( "test_results.json", "w+" )          # Vin - add date/time to file name
    fp.write( json.dumps(results, indent=4, sort_keys=True) )
    fp.write( "\n" )
    fp.close()


