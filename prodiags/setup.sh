#!/bin/bash
# Script to install python3 required packages

# Globals
res=""

which pip3 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
	echo "Pip3 is required as part of Python 3.x.x installation to run this tool"
	exit 1
fi

pip3 install scp requests pathlib paramiko 1> /dev/null 2> /dev/null
if [ $? -eq 1 ]; then
	pip3 install scp requests pathlib paramiko
	echo "Failed to install some of the components"
	exit 1
else
	echo "$0 completed successfully!"
fi
