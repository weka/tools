#WEKAPP-550018


#(for MASTER in $(ps -eo pid,args | grep "wekanode --slot [1-9]"|awk '{print $1}' | sort -nu ) ; do for CHILD in $(ps -L -p ${MASTER} | grep wekanode-pool | awk '{print $2}'| sort -nu) ; do taskset -p $CHILD | awk -F: '{print $2}' ; done ; done) | sort -u
