# wekatester
Performance test weka clusters with distributed fio

Includes fio both consistency (versions vary) and convienience. 


```
# ./wekatester --help
usage: wekatester.py [-h] -d DIRECTORY [-w WORKLOAD] [--fio-bin LOCAL_FIO]
                     [-V] [-v]
                     [server ...]

Basic Performance Test a Network/Parallel Filesystem

positional arguments:
  server                One or more Servers to use a workers

optional arguments:
  -h, --help            show this help message and exit
  -d DIRECTORY, --directory DIRECTORY
                        target directory on the workers for test files
  -w WORKLOAD, --workload WORKLOAD
                        workload definition directory (a subdir of fio-
                        jobfiles)
  --fio-bin LOCAL_FIO   Specify the fio binary on the target servers (default
                        /usr/bin/fio)
  -V, --version         Display version number
  -v, --verbosity       increase output verbosity
```                        

# Basics
fio is a benchmark for IO, and is quite popular.  However, running it in a distributed fashion across multiple servers can be a bit of a bear to manage, and the output can be quite difficult to read.

The idea of wekatester is to bring some order to this chaos.   To make running fio in a distributed environment, wekatester automatically distributes and executes fio commands on remote servers, runs a standard set of benchmark workloads, and summarizes the results.

# Options
`servers` - a list of servers to use as workers.

`-d DIRECTORY` sets the directory where the benchmark files will be created.  This is a required argument.

`-w WORKLOAD` get fio jobfile specifications from a subdirectory of fio-jobfiles.   The default is 'default'.  Currently, there are 2 discributed with wekatester, "default" (4-corners tests), and "mixed", a set of 70/30 RW workloads.  You can add your own directories, and use the with -w.

`--fio-bin` Default is `/usr/bin/fio`.  You can use this argument to set a different location.

`-v` Sets verbosity.  `-vv`, and `-vvv` are supported to set ever increasing verbosity.

# Output
The output will be summarized after each workload run, and all results are writting to a log file.

Typical output will look something like this:
```
starting test run for job 011-bandwidthR.job on <hostname> with <n> workers:
    read bandwidth: 9.37 GiB/s
    total bandwidth: 9.37 GiB/s
    average bandwidth: 2.34 GiB/s per host

starting test run for job 012-bandwithW.job on <hostname> with <n> workers:
    write bandwidth: 7.72 GiB/s
    total bandwidth: 7.72 GiB/s
    average bandwidth: 1.93 GiB/s per host

starting test run for job 021-latencyR.job on <hostname> with <n> workers:
    read latency: 237 us

starting test run for job 022-latencyW.job on <hostname> with <n> workers:
    write latency: 180 us

starting test run for job 031-iopsR.job on <hostname> with <n> workers:
    read iops: 376,697/s
    total iops: 376,697/s
    average iops: 94,174/s per host

starting test run for job 032-iopsW.job on <hostname> with <n> workers:
    write iops: 302,132/s
    total iops: 302,132/s
    average iops: 75,533/s per host

Writing raw fio results to results_2025-10-07_1112.json
```
The raw output is the actual raw JSON output from the FIO commands.