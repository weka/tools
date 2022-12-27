# Weka resource generator 
Resource generator for weka containers

## usage:
resources_generator.py --net <net-devices> [options]

optional arguments:
  
  `--allow-all-disk-types`
  Detect all available (non-rotational) devices. If not specified, only NVME devices will be detected. For allowing rotating disks - please add '--allow-rotational' as well
  
  `--allow-rotational`
  Detect rotational disks
  
  `--compute-core-ids COMPUTE_CORE_IDS [COMPUTE_CORE_IDS ...]`
  Specify manually which CPUs to allocate for COMPUTE
                        nodes
  
  `--compute-dedicated-cores COMPUTE_DEDICATED_CORES`
  Specify how many cores will be dedicated for COMPUTE
                        nodes
  
  `--compute-memory COMPUTE_MEMORY`
  Specify how much total memory should be allocated for
                        COMPUTE, argument should be value and unit without
                        whitespace (i.e 10GiB, 1024B, 5TiB etc.)
  
  `--core-ids CORE_IDS [CORE_IDS ...]`
  Specify manually which CPUs to allocate for weka nodes
  
  `--drive-core-ids DRIVE_CORE_IDS [DRIVE_CORE_IDS ...]`
  Specify manually which CPUs to allocate for DRIVE
                        nodes
  
  `--drive-dedicated-cores DRIVE_DEDICATED_CORES`
  Specify how many cores will be dedicated for DRIVE
                        nodes
  
  `--drives DRIVES [DRIVES ...]`
  Specify drives to be used separated by whitespaces
                        (override automatic detection)
  
  `--frontend-core-ids FRONTEND_CORE_IDS [FRONTEND_CORE_IDS ...]`
  Specify manually which CPUs to allocate for FRONTEND
                        nodes
  
  `--frontend-dedicated-cores FRONTEND_DEDICATED_CORES`
  Specify how many cores will be dedicated for FRONTEND
                        nodes
  
  `--max-cores-per-container MAX_CORES_PER_CONTAINER` 
  Override the default max number of cores per
                        container: 19, if provided - new value must be lower
  
 
  `--minimal-memory`
  Set each container hugepages memory to 1.4 GiB *
                        number of io nodes on the container
  
  `--net net-devices [net-devices ...]`
  Specify net devices to be used separated by
                        whitespaces
  
  `--no-rdma`
  Don't take RDMA support into account when computing
                        memory requirements, false by default
  
  `--num-cores NUM_CORES`
  Override the auto-deduction of number of cores
  
  `--path PATH`
  Specify the directory path to which the resources
                        files will be written, default is '.'
  
  `--spare-cores SPARE_CORES`
  Specify how many cores to leave for OS and non weka
                        processes
  
  `--spare-memory SPARE_MEMORY`
  Specify how much memory should be reserved for non-
                        weka requirements, argument should be value and unit
                        without whitespace (i.e 10GiB, 1024B, 5TiB etc.)
  
  `--weka-hugepages-memory WEKA_HUGEPAGES_MEMORY`
  Specify how much memory should be allocated for
                        COMPUTE, FRONTEND and DRIVE nodes.argument should be
                        value and unit without whitespace (i.e 10GiB, 1024B,
                        5TiB etc.)
  
  `-f, --force`
  Force continue in cases of prompts
  
  `-h, --help`
  show this help message and exit
  
  `-v, --verbose`
  Sets console log level to DEBUG
  
