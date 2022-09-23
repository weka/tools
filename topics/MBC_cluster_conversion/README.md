# SBC to MBC convertor

# requirements to run the script on the whole cluster

- Moving the three components into /tmp/ (convert_cluster_to_mbc.sh, mbc_divider_script.py, resources_generator.py)
- Having passwordless ssh to all BE machines and passwordless sudo for the user.
- No active alerts
- The BE host has no converged NODE roles (i.e. each node should be either FRONTEND, COMPUTE, or DRIVE)
- The BE MUST NO BE MOUNTED, a backend with no (protocols are fine)
- For protocols: there should be at list minimum+1 hosts serving the protocol

# components

The converter has 3 components for it to run, they are all located inside the container and can be copied via weka local run in /weka/hostside
pull from tools repository https://github.com/weka/tools
or pull from the container:

```jsx
 $ weka local run
(weka_container):~# cp /weka/hostside/resources_generator.py /data/tmp/
(weka_container):~# cp /weka/hostside/mbc_divider_script.py /data/tmp/
(weka_container):~# cp /weka/hostside/convert_cluster_to_mbc.sh /data/tmp/
(weka_container):~# exit
exit
$ ls /opt/weka/data/default_4.0.1.3331-6cd38f8cbcdd576ee198cfd219b0905f/tmp/
convert_cluster_to_mbc.sh  mbc_divider_script.py      resources_generator.py/h
```

In order to convert full cluster place all files in the /tmp dir

## Running

```jsx
./convert_cluster_to_mbc.sh #will convert the whole cluster to MBC
```

flags for the conversion script:

```jsx
OPTIONS:
  -f force override of backup resources file if exist
  -a run with active alerts
  -s skip failed hosts
  -d override drain grace period for s3 in seconds
  -b to perform conversion on a single host
  -l log file will be saved to this location insted of current dir
  -h show this help string
```

# Stopping

In order to stop create a stop_file in the running directory