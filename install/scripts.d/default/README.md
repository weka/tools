# Default scripts

These scripts are executed when wekatester is used with without a `--workload` parameter or with `--workload default`

These are intended to be run *before* installing WEKA

Use the `ta` scripts to debug after joining a cluster, and with `client` scripts to prep a client

## Return codes
The scripts return a return code indicating the status of the test:
- 0   = PASS
- 255 = HARDFAIL (Terminate further testing)
- 254 = WARN
- anything else = FAIL