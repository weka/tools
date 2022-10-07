#!/usr/bin/env bash

#COLORS
export NOCOLOR="\033[0m"
export CYAN="\033[0;36m"
export YELLOW="\033[1;33m"
export RED="\033[0;31m"
export GREEN="\033[1;32m"
export BLUE="\033[1;34m"

CLUSTERNAME=$(weka status -J | awk '/"name":/ {print $2}' | cut -d'"' -f2)

#ALL
cluster_lease_timeout_msecs=18000
heartbeat_grace_msecs=20000
heartbeat_timeout_msecs=5000
raft_term_timeout_msecs=4500
raid_journal_hound_bytes_per_sec=1073741824
trace_load_localstate_entries=true
fe_ssd_extra_load_threshold=250
max_read_blocks=128
ssd_base_load=24
rdma_readbinding_expiration_timeout_secs=240
allow_prefix_mismatch_on_expected_prefix=1151546163

function NOTICE() {
echo -e "\n${CYAN}$1${NOCOLOR}"
}

function GOOD() {
echo -e "${GREEN}$1${NOCOLOR}"
}

function WARN() {
echo -e "${YELLOW}$1${NOCOLOR}"
}

function BAD() {
echo -e "${RED}$1${NOCOLOR}"
}

CLUSTERLEASE=$(weka debug override list -o key,value --no-header | grep cluster_lease_timeout_msecs | awk '{print $2}')
HBGRACE=$(weka debug override list -o key,value --no-header | grep heartbeat_grace_msecs | awk '{print $2}')
HBTIMEOUT=$(weka debug override list -o key,value --no-header | grep heartbeat_timeout_msecs | awk '{print $2}')
RAFT=$(weka debug override list -o key,value --no-header | grep raft_term_timeout_msecs | awk '{print $2}')
RAIDJOURNAL=$(weka debug override list -o key,value --no-header | grep raid_journal_hound_bytes_per_sec | awk '{print $2}')
TRACE=$(weka debug override list -o key,value --no-header | grep trace_load_localstate_entries | awk '{print $2}')
FESSD=$(weka debug override list -o key,value --no-header | grep fe_ssd_extra_load_threshold | awk '{print $2}')
MAXREAD=$(weka debug override list -o key,value --no-header | grep max_read_blocks | awk '{print $2}')
SSDBASE=$(weka debug override list -o key,value --no-header | grep ssd_base_load | awk '{print $2}')
RDMAWRITE=$(weka debug override list -o key,value --no-header | grep rdma_force_disable_write | awk '{print $1}')
RDMABINDING=$(weka debug override list -o key,value --no-header | grep rdma_readbinding_expiration_timeout_secs | awk '{print $2}')
MISMATCHPREFIX=$(weka debug override list -o key,value,bucketId --no-header | grep allow_prefix_mismatch_on_expected_prefix | awk '{print $2,$3}')
STALLCOPIES=$(weka debug override list -o key,value --no-header | grep stall_secondary_copies_seek | awk '{print $1}')
GRIMREAPER=$(weka status -J | grep -A1 grim_reaper | grep enabled | awk '{print $2}' | tr -d ',')


function _clusterlease() {
if [ -z "$CLUSTERLEASE" ]; then 
    WARN "Missing Manual Override Key cluster_lease_timeout_msecs"
elif [ "$CLUSTERLEASE" != "$cluster_lease_timeout_msecs" ]; then
    WARN "Overide setting incorrect set cluster_lease_timeout_msecs should be $cluster_lease_timeout_msecs"
fi
}

function _hbgrace() {
if [ -z "$HBGRACE" ]; then 
    WARN "Missing Manual Override Key heartbeat_grace_msecs"
elif [ "$HBGRACE" != "$heartbeat_grace_msecs" ]; then
    WARN "Overide setting incorrect set heartbeat_grace_msecs should be $heartbeat_grace_msecs"
fi
}

function _hbtimeout() {
if [ -z "$HBTIMEOUT" ]; then 
    WARN "Missing Manual Override Key heartbeat_timeout_msecs"
elif [ "$HBTIMEOUT" != "$heartbeat_timeout_msecs" ]; then
    WARN "Overide setting incorrect set heartbeat_timeout_msecs should be $heartbeat_timeout_msecs"
fi
}

function _raft() {
if [ -z "$RAFT" ]; then 
    WARN "Missing Manual Override Key raft_term_timeout_msecs"
elif [ "$RAFT" != "$raft_term_timeout_msecs" ]; then
    WARN "Overide setting incorrect set raft_term_timeout_msecs should be $raft_term_timeout_msecs"
fi
}

function _raidjournal() {
if [ -z "$RAIDJOURNAL" ]; then 
    WARN "Missing Manual Override Key raid_journal_hound_bytes_per_sec"
elif [ "$RAIDJOURNAL" != "$raid_journal_hound_bytes_per_sec" ]; then
    WARN "Overide setting incorrect set raid_journal_hound_bytes_per_sec should be $raid_journal_hound_bytes_per_sec"
fi
}

function _trace() {
if [ -z "$TRACE" ]; then 
    WARN "Missing Manual Override Key trace_load_localstate_entries"
elif [ "$TRACE" != "$trace_load_localstate_entries" ]; then
    WARN "Overide setting incorrect set trace_load_localstate_entries should be $trace_load_localstate_entries"
fi
}

function _fessd() {
if [ -z "$FESSD" ]; then 
    WARN "Missing Manual Override Key fe_ssd_extra_load_threshold"
elif [ "$FESSD" != "$fe_ssd_extra_load_threshold" ]; then
    WARN "Overide setting incorrect set fe_ssd_extra_load_threshold should be $fe_ssd_extra_load_threshold"
fi
}

function _maxread() {
if [ -z "$MAXREAD" ]; then 
    WARN "Missing Manual Override Key max_read_blocks"
elif [ "$MAXREAD" != "$max_read_blocks" ]; then
    WARN "Overide setting incorrect set max_read_blocks should be $max_read_blocks"
fi
}

function _ssdbase() {
if [ -z "$SSDBASE" ]; then 
    WARN "Missing Manual Override Key ssd_base_load"
elif [ "$SSDBASE" != "$ssd_base_load" ]; then
    WARN "Overide setting incorrect set ssd_base_load should be $ssd_base_load"
fi
}

function _rdmawrite() {
if [ -z "$RDMAWRITE" ]; then 
    WARN "Missing Manual Override Key rdma_force_disable_write"
fi
}

function _rdmabinding() {
if [ -z "$RDMABINDING" ]; then 
    WARN "Missing Manual Override Key rdma_readbinding_expiration_timeout_secs"
elif [ "$RDMABINDING" != "$rdma_readbinding_expiration_timeout_secs" ]; then
    WARN "Overide setting incorrect set rdma_readbinding_expiration_timeout_secs should be $rdma_readbinding_expiration_timeout_secs"
fi
}

function _prefixmismatch() {
if [ -z "$MISMATCHPREFIX" ]; then 
    WARN "Missing Manual Override Key allow_prefix_mismatch_on_expected_prefix"
elif [ "$MISMATCHPREFIX" != "$allow_prefix_mismatch_on_expected_prefix" ] || [ $(echo $MISMATCHPREFIX | cut -d' ' -f2) -ne 66 ] ; then
    WARN "Overide setting incorrect set allow_prefix_mismatch_on_expected_prefix should be $allow_prefix_mismatch_on_expected_prefix on BucketId 66)"
fi
}

function _stallcopies() {
if [ -z "$STALLCOPIES" ]; then 
    WARN "Missing Manual Override Key stall_secondary_copies_seek"
fi
}

function _grimreaper() {
if [ "$GRIMREAPER" == "true" ]; then 
    WARN "Grim Reaper should be disabled"
fi
}



NOTICE "VERIFYING OPTIMAL SETTINGS"

if [ "$CLUSTERNAME" == starkeast01 ]; then
    _clusterlease
    _hbgrace
    _hbtimeout
    _maxread
    _raft
    _raidjournal
    _rdmawrite
    _rdmabinding
    _trace
    _grimreaper
fi

if [ "$CLUSTERNAME" == starkeast02 ]; then
    _clusterlease
    _fessd
    _hbgrace
    _hbtimeout
    _maxread
    _raft
    _raidjournal
    _rdmawrite
    _rdmabinding
    _ssdbase
    _trace
    _grimreaper
fi

if [ "$CLUSTERNAME" == stark03-intel ]; then
    _clusterlease
    _hbgrace
    _hbtimeout
    _prefixmismatch
    _stallcopies
    _grimreaper
fi

NOTICE "ALL CHECKS COMPLETE"