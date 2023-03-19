# wekatester
Performance test weka clusters with distributed fio

Includes fio both consistency (versions vary) and convienience. 


```
usage: wekatester [-h] [-v] [-c] [-s] [-d DIRECTORY] [-w WORKLOAD] [-o]
                  [-a] [--no-weka] [--auth AUTHFILE]
                  [server [server ...]]

Acceptance Test a weka cluster

positional arguments:
  server                One or more Servers to use a workers (weka mode
                        [default] will get names from the cluster)

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbosity       increase output verbosity
  -c, --clients         run fio on weka clients
  -s, --servers         run fio on weka servers
  -d DIRECTORY, --directory DIRECTORY
                        target directory for workload (default is /mnt/weka)
  -w WORKLOAD, --workload WORKLOAD
                        workload definition directory (a subdir of fio-
                        jobfiles)
  -o, --output          run fio with output file
  -a, --autotune        automatically tune num_jobs to maximize performance
                        (experimental)
  --no-weka             force non-weka mode
  --auth AUTHFILE       auth file for authenticating with weka (default is
                        auth-token.json)

```                        

# Basics
fio is a benchmark for IO, and is quite popular.  However, running it in a distributed fashion across multiple servers can be a bit of a bear to manage, and the output can be quite difficult to read.

The idea of wekatester is to bring some order to this chaos.   To make running fio in a distributed environment, wekatester automatically distributes and executes fio commands on remote servers, runs a standard set of benchmark workloads, and summarizes the results.  It's also aware of Weka clusters, in particular.

# Options
Servers - a list of weka servers to connect to via the API, or when combined with --no-weka, a list of servers to use as workers.

`-c` makes wekatester query the cluster for what clients exist and uses ALL of them as workers

`-s` makes wekatester query the cluster for what backends exist and uses ALL of them as workers

`-d DIRECTORY` sets the directory where the benchmark files will be created.  Default is /mnt/weka

`-w WORKLOAD` get fio jobfile specifications from a subdirectory of fio-jobfiles.   The default is 'default'.  Currently, there are 2 discributed with wekatester, "default" (4-corners tests), and "mixed", a set of 70/30 RW workloads.  You can add your own directories, and use the with -w.

`-o` will create an output file with all the fio output in it in JSON format.

`-a` automatically adjust numjobs= to 2x the number of available cores.  Works on all workloads.

`-v` Sets verbosity.  `-vv`, and `-vvv` are supported to set ever increasing verbosity.

`--no-weka` Assumes the Servers are not weka servers or clients and just runs the workload on them

`--auth` Specify an alternate file instead of the default auth-token.json
