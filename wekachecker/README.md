# sns-wekachecker
Validates hosts are ready to run Weka


New Version 2.0 - threaded implementation greatly improves performance

Many small tweaks

# running wekachecker

1. Either clone the repository or download release tarball and unpack
2. cd to the wekachecker directory
3. run "./wekachecker.py <list of ips>", where the ips are the dataplane network ips
4. If it reports ANY warnings or errors, run "./report.py test_results.json" for details
  
Optional arguments:
  * Run with -c to restrict tests to the cluster-wide tests (ping, ssh, and timesync tests)
  * Run with -s to restrict tests to the server-specific tests (most of the tests)
  * Run with -p to restrict tests to the iperf network performance tests
  
  optional arguments may be combined.  For example, "-c -s"
  
