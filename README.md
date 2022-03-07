# Tools

Tools to help with Weka clusters

## How-to install a weka cluster using these tools, aka Configuration Guide

o log in as 'root' on one of the servers that will be a Weka Server

o Download the weka code from get.weka.io to root's $HOME

o Git clone this repo into root's $HOME

o Go into `tools/`

o Start with the `wekachecker` - run it for all dataplane ips (if more than one interface, do them in sets - is ib0 on all hosts, then run again with ib1 of all hosts)

o Fix/investigate any issues that `wekachecker` WARNs or FAILs, re-run until it looks good

o Go to the `install/` subdir

o Use wekadeploy to copy and install the Weka code on all nodes (use dataplane for best performance)

o Verify all nodes are in STEM mode (this is indicated at the end of the wekadeploy)

o Use `wekaconfig` to generate a configuration

o Check the configuration/`config.txt` - wekaconfig cannot anticipate all possible configurations, so may generate something unwanted or unexpected

o Apply the configuration by executing the commands in the configuration (`config.txt`)

o Use `weka local resources`, `weka status`, `weka cluster nodes`, and `weka cluster drives` to look for any errors in the configuration

o Use `weka cluster start-io` to start the cluster

o Use `weka status` to verify that all looks good, fix if needed

o Create filesystem groups and filesystems

o Optionally, configure S3 data stores and auxiliary services (NFS, SMB, S3), security, etc.

## subdirs
The sub-directories of this repository contain various tools.

## install
General installation tools

## postinstall
General post-installation tools

## preinstall
General pre-installation tools

## topics
Miscellaneous tools grouped by topics

## wekachecker
Check if hosts are ready for Weka

## wekatester
Runs fio benchmarks in distributed mode with ease - easy performance testing
