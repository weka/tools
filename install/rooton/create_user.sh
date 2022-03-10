#!/bin/bash
# This script would generated superuser weka
# Please run as root user only in terminal mode

user=`whoami`
created_user=""
created_user_password=""

if [ "$user" != "root" ]; then
	echo "Sorry, this script can run as root user only.."
	exit 1
fi

echo -n "Please enter priviliged username: "; read created_user
if [ -z "$created_user" ]; then 
	echo "Sorry can't accept empty string.."; exit 1
fi
echo -n "Please enter priviliged user password: "; read -s created_user_password
if [ -z "$created_user_password" ]; then 
	echo "Sorry can't accept empty string.."; exit 1
fi
# Add user
# Check if that user already exists, if yes, we will ask the running user for permission to delete that directory
if [ -d /home/$crated_user ]; then
	echo "\r"
	echo -n "The following user exists, would you like to remove it? (yes/no): "; read ret;
	case $ret in
		"yes"|"y"|"YES"|"Yes"|"Y" ) userdel $created_user 1> /dev/null 2> /dev/null; deluser $created_user 1> /dev/null 2> /dev/null; rm -rf /home/$created_user;;
		"no"|"n"|"NO"|"No"|"N"	  ) echo "Cannot proceed if the /home/$created_user directory exists"; exit 1;;
			* 		  ) echo "Please enter (yes/no)"; exit 1;;	
	esac
fi
adduser $created_user
# Modify user default password
echo -e "$created_user_password\n$created_user_password" | passwd $created_user
# Add user weka to /etc/sudoers.d/
usermod -aG sudo $created_user 1> /dev/null 2> /dev/null
usermod -aG wheel $created_user 1> /dev/null 2> /dev/null
echo "$created_user  ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/$created_user

