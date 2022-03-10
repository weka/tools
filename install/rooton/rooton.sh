#!/bin/bash
# Written by Daniel Slabodar on 1/5/2022 (bugz to: daniel@i-clef.com daniels@weka.io) for Weka.IO
# Script to login to remote host and configure passwordless connectivity back to system from which the login is performed for a user and root
# Script to be run as a user with root permissions

# Globals
local_root_password=""
running_user=""
remote_root_password=""
user_password=""
hide_output="true"
set_expect=""
set_sshpass=""
first_ip=""
ip_range=( "" )
#ip_range=( "172.29.0.134" "172.29.0.135" "172.29.0.136" "172.29.0.137" "172.29.0.138" "172.29.0.139" "172.29.0.140" "172.29.0.141" )

# Functions
function check_sshpass () {

which sshpass 1> /dev/null 2> /dev/null
if [ $? -ne 0 ]; then
	echo "Could not find sshpass utility, will try to deploy a local version"
	if [ "$OSTYPE" != "linux-gnu" ]; then
		echo "Found non Linux OS type, deploying mac sshpass version"
		deploy_sshpass mac
	else
		echo "Found Linux OS type, deploying Linux sshpass version"
		deploy_sshpass linux
	fi
fi

}

function read_passwords () {
# Function to read user input for root and user passwords
if [ -z $running_user ]; then
	echo -n "Please enter a priviliged remote username: "; read "running_user"
	if [ -z "$running_user" ]; then
		echo -e "\r"
		echo "Entered empty username, please try again..."
		exit 1
	else
		if [ "$running_user" == "root" ]; then
			echo "We are unable to set sshless connectivity for root user, this is highly stupid"
			exit 1
		fi
	fi
else
	if [ "$running_user" == "root" ]; then
		echo "We are unable to set sshless connectivity for root user, this is highly stupid"
		exit 1
	fi
fi
	
if [ -z $user_password ]; then
	echo -n "Please enter priviliged remote user $running_user password: "; read -s user_password
	if [ -z "$user_password" ]; then
		echo -e "\r"
		echo "Entered empty password, please try again..."
		exit 1
	else
		echo -e "\r"
	fi
fi
if [ -z $remote_root_password ]; then
	echo -n "Please enter remote root password: "; read -s remote_root_password
	if [ -z "$remote_root_password" ]; then
		echo -e "\r"
		echo "Entered empty password, please try again..."
		exit 1
	else
		echo -e "\r"
	fi
fi
}

function deploy_sshpass () {
# Will try to invoke locally compiled sshpass to bypass internet installation issues or missing packages
sshpass_type="$1"

if [ "$sshpass_type" == "mac" ]; then
	su - root -c cp `pwd`/sshpass_mac /usr/local/bin/sshpass
fi

if [ "$sshpass_type" == "linux" ]; then
	su - root -c cp `pwd`/sshpass /usr/bin/sshpass
fi

}

function sshpass_run () {
# Function to perform operations with sshpass
# Root ssh would be allowed only if PermitRootLogin yes is set in /etc/ssh/sshd_config and service properly restarted on the server
cmd="$1"
ip="$2"
selected_user="$3"
selected_password="$4"

if [ "$hide_output" == "true" ]; then
	if [ "$OSTYPE" != "linux-gnu" ]; then
		sshpass -p "$user_password" ssh -l$running_user $ip "echo \"$selected_password\" | su - $selected_user -c \"$cmd\"" 1> /dev/null 2> /dev/null
		return $?
	else
		sshpass -p "$user_password" ssh -l$running_user $ip echo "$selected_password" | su - $selected_user -c "$cmd" 1> /dev/null 2> /dev/null
		return $?
	fi
else
	echo "command: $cmd"
	if [ "$OSTYPE" != "linux-gnu" ]; then
		sshpass -p "$user_password" ssh -l$running_user $ip "echo \"$selected_password\" | su - $selected_user -c \"$cmd\""
		echo $?; return $?
	else
		sshpass -p "$user_password" ssh -l$running_user $ip "echo "$selected_password" | su - $selected_user -c \"$cmd\""
		echo $?; return $?
	fi
fi

}

function check_ssh_perm () {
# Function to check if ssh allows to connect
ip="$1"
if [ "$OSTYPE" != "linux-gnu" ]; then
	sshpass -p "$user_password" ssh -l$running_user $ip "echo \"$remote_root_password\" | su - root -c \"echo\"" 1> /dev/null 2> /dev/null
	if [ $? -ne 0 ]; then
		return 1
	else
		return 0
	fi
else
	sshpass -p "$user_password" ssh -l$running_user $ip echo "$remote_root_password" | su - root -c "echo" 1> /dev/null 2> /dev/null
	if [ $? -ne 0 ]; then
		return 1
	else
		return 0
	fi
fi
}

function sshpass_sequence () {
ip="$1"
first="$2"
if [ "$set_sshpass" == "true" ]; then
	if [ "$first" == "1" ]; then
		# Setting first_ip address
		first_ip=$ip
		# Permit root login for ssh
		sshpass_run "sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config" $first_ip root $remote_root_password
		# Restart ssh service
		sshpass_run "systemctl restart ssh*.service" $first_ip root $remote_root_password
		# Set ssh client /server settings to disable asking to add a new ssh key to known_hosts file
		sshpass_run "sed -i 's/.*StrictHostKeyChecking.*/StrictHostKeyChecking no/g' /etc/ssh/ssh_config" $first_ip root $remote_root_password
		# Set sshless connectivity, this is generated only for first ip address, copy key to second and so on servers from first...
		sshpass -p "$user_password" ssh $running_user@$ip "mkdir -p /home/$running_user/.ssh"
		sshpass -p "$user_password" ssh $running_user@$ip "chmod 700 -R /home/$running_user/.ssh/"
		sshpass -p "$user_password" ssh $running_user@$ip "rm -rf /home/$running_user/.ssh/id_rsa*"
		if [ "$OSTYPE" != "linux-gnu" ]; then
			sshpass -p "$user_password" ssh $running_user@$ip "ssh-keygen -t rsa -f /home/$running_user/.ssh/id_rsa -N \\\"\\\" -q"
		else
			sshpass -p "$user_password" ssh $running_user@$ip "ssh-keygen -t rsa -f /home/$running_user/.ssh/id_rsa -N \"\" -q"
		fi
		sshpass -p "$user_password" ssh $running_user@$ip "cat /home/$running_user/.ssh/id_rsa.pub | cat >> /home/$running_user/.ssh/authorized_keys"
		sshpass -p "$user_password" ssh $running_user@$ip "sed -i 's/= '$running_user'.*\$/= /g' /home/$running_user/.ssh/authorized_keys"
		sshpass -p "$user_password" ssh $running_user@$ip "sed -i 's/= '$running_user'.*\$/= /g' /home/$running_user/.ssh/id_rsa.pub"
		sshpass -p "$user_password" ssh $running_user@$first_ip "chmod 700 -R /home/$running_user/.ssh/"
		mkdir -p /tmp/ssh_copy
		sshpass -p "$user_password" scp $running_user@$first_ip:/home/$running_user/.ssh/* /tmp/ssh_copy/
	else
		# Permit root login for ssh
		sshpass_run "sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config" $ip root $remote_root_password
		# Restart ssh service
		sshpass_run "systemctl restart ssh*.service" $ip root $remote_root_password
		# Set ssh client /server settings to disable asking to add a new ssh key to known_hosts file
		sshpass_run "sed -i 's/.*StrictHostKeyChecking.*/StrictHostKeyChecking no/g' /etc/ssh/ssh_config" $ip root $remote_root_password
		# Prepping .ssh env for user
		sshpass -p "$user_password" ssh $running_user@$ip "mkdir -p /home/$running_user/.ssh"
		sshpass -p "$user_password" ssh $running_user@$ip "chmod 700 -R /home/$running_user/.ssh/"
		# Copy .ssh/ keys to local dir
		sshpass -p "$user_password" scp /tmp/ssh_copy/* $running_user@$ip:/home/$running_user/.ssh/
	fi

else
	echo "SSHpass is not installed properly, cannot continue."
	exit 1
fi

}		

function check_host_alive () {
# Function to check if the host is alive
ip="$1"
if [ "$hide_output" == "true" ]; then
	ping -c 1 -i 1 -W 2 $ip 1> /dev/null 2> /dev/null
	if [ $? -ne 0 ]; then
		return 1
	else
		return 0
	fi
else
	ping -c 1 -i 1 -W 2 $ip 
	if [ $? -ne 0 ]; then
		return 1
	else
		return 0
	fi
fi
}

function end_prog () {
if [ "$hide_output" == "false" ]; then
	rm -rf /tmp/ssh_copy*
	echo -e "\r"
fi
}

## Main
# If there are no command line args, it means that there is only a single host to configure the parameters
# Command line parameters could include a single IP addresses, a series of IP addresses, seperated by comma

read_passwords
check_sshpass 

if [ $? -eq 0 ]; then
	set_sshpass="true"
else
	set_sshpass="false"
fi

#
if [ $# -eq 0 ]; then
	echo "Input parameters are not entered, checking internal configration"
	if [ ${#ip_range[@]} -ne 0 ]; then
		range=${#ip_range[@]}
		# setting first server then the rest
		check_host_alive ${ip_range[0]}
		if [ $? -ne 0 ]; then
			echo "Host: ${ip_range[0]} is down"
		else
			check_ssh_perm ${ip_range[0]}
			if [ $? -eq 0 ]; then
				sshpass_sequence ${ip_range[0]} 1
			else
				echo "Host: ${ip_range[0]} password is probably incorrect, unable to connect as priveleged $running_user user"
			fi
		fi
		for (( i=1; i<${range}; i++ )); do
			check_host_alive ${ip_range[$i]}
			if [ $? -ne 0 ]; then
				echo "Host: ${ip_range[$i]} is down"
			else
				check_ssh_perm ${ip_range[$i]}
				if [ $? -eq 0 ]; then
					sshpass_sequence ${ip_range[$i]} 0
				else
					echo "Host: ${ip_range[$i]} password is probably incorrect, unable to connect as priveleged $running_user user"
				fi
			fi
		done
	fi
else
	ip_range=( "$@" )
	range=${#ip_range[@]}
	# setting first server then the rest
	check_host_alive ${ip_range[0]}
	if [ $? -ne 0 ]; then
		echo "Host: ${ip_range[0]} is down"
	else
		check_ssh_perm ${ip_range[0]}
		if [ $? -eq 0 ]; then
			sshpass_sequence ${ip_range[0]} 1
		else
			echo "Host: ${ip_range[0]} password is probably incorrect, unable to connect as priveleged $running_user user"
		fi
	fi
	for (( i=1; i<${range}; i++ )); do
		check_host_alive ${ip_range[$i]}
		if [ $? -ne 0 ]; then
			echo "Host: ${ip_range[$i]} is down"
		else
			check_ssh_perm ${ip_range[$i]}
			if [ $? -eq 0 ]; then
				sshpass_sequence ${ip_range[$i]} 0
			else
				echo "Host: ${ip_range[$i]} password is probably incorrect, unable to connect as privileged $running_user user"
			fi
		fi
	done
fi

end_prog

