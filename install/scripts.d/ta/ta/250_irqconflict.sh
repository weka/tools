#!/bin/bash

DESCRIPTION="Check for IRQ conflicts"
SCRIPT_TYPE="parallel"

rc=0

irq_mismatches=$(journalctl -b | awk -F '[()]' '/genirq: Flags mismatch.*uio_pci_generic/ { print $2" "$4 }')

oldifs=$IFS IFS=$'\n'
for line in $irq_mismatches; do
	echo
	echo "IRQ conflict between: $line"

	if [ "$FIX" = 'True' ] && [ "$UID" -eq 0 ]; then
		case $line in
			*i801*)
				i801_dsbl='/sys/module/i2c_i801/parameters/disable_features'
				if [ -f "$i801_dsbl" ] && [ "$(cat "$i801_dsbl")" -ne 16 ]; then
					echo '--fix specified, disabling interrupts for i2c_i801 now'
					echo '16' > /sys/module/i2c_i801/parameters/disable_features
					rc=1
				fi
				if [ ! -f /etc/modprobe.d/i2c_i801.conf ]; then
					echo '--fix specified, disabling interrupts for i2c_i801 permanently in'
					echo '/etc/modprobe.d/i2c_i801.conf'
					echo 'options i2c_i801 disable_features=0x10' > /etc/modprobe.d/i2c_i801.conf
					rc=1
				fi
				;;

			*hpilo*)
				if [ -d /sys/module/hpilo/ ]; then
					echo '--fix specified, disabling hpilo now'
					modprobe -r hpilo
					rc=1
				fi
				if [ ! -f /etc/modprobe.d/hpilo-blacklist.conf ]; then
					echo '--fix specified, disabling hpilo on boot'
					cat <<- 'EOF' > /etc/modprobe.d/hpilo.conf
					blacklist hpilo
					install hpilo /bin/false
					EOF
					rc=1
				fi
				;;

			*ehci*)
				if [ ! -f /etc/default/grub.d/ehci_hcd.conf ]; then
					echo '--fix specified, updating GRUB configuration to disable ehci_hcd and ehci_pci (USB 2.0) on boot.'
					echo 'Restart required for this to take effect.'
					if [ "$ID" = 'ubuntu' ]; then
						echo 'GRUB_CMDLINE_LINUX="$GRUB_CMDLINE_LINUX initcall_blacklist=ehci_pci_init,ehci_hcd_init"' > /etc/default/grub.d/ehci_hcd.conf
						update-grub
					elif ! grep -qE '^GRUB_CMDLINE_LINUX=.*initcall_blacklist=ehci_pci_init,ehci_hcd_init' /etc/default/grub; then
						sed -i '/^GRUB_CMDLINE_LINUX/s/"$/ initcall_blacklist=ehci_pci_init,ehci_hcd_init"/' /etc/default/grub
						grub2-mkconfig -o /boot/grub2/grub.cfg
					fi
					rc=1
				elif [ -d /sys/module/ehci_hcd/ ]; then
					echo 'Restart required to disable ehci_hcd and ehci_pci'
					rc=1
				fi
				;;
		esac

	else
		if [ "$FIX" = 'True' ]; then
			echo '--fix specified but not running as root, will not fix'
		fi

		case $line in
			*i801*)
				echo 'IRQs can be disabled for i2c_i801 by running:'
				echo "    echo '16' > /sys/module/i2c_i801/parameters/disable_features"
				echo "    echo 'options i2c_i801 disable_features=0x10' > /etc/modprobe.d/i2c_i801.conf"
				echo 'Or to disable i2c_i801 altogether:'
				echo '    modprobe -r i2c_i801'
				echo "    printf 'blacklist i2c_i801\\ninstall i2c_i801 /bin/false\\n' > /etc/modprobe.d/i2c_i801.conf"
				rc=1
				;;

			*hpilo*)
				echo 'hpilo does not allow interrupts to be disabled; it therefore must be disabled by running:'
				echo "    printf 'blacklist hpilo\\ninstall hpilo /bin/false\\n' > /etc/modprobe.d/hpilo-blacklist.conf"
				rc=1
				;;

			*ehci*)
				echo 'EHCI driver is built-in (not a module), therefore it must be disabled via the kernel command line, e.g.:'
				echo 'Ubuntu:'
				echo "    echo 'GRUB_CMDLINE_LINUX=\"\$GRUB_CMDLINE_LINUX initcall_blacklist=ehci_pci_init,ehci_hcd_init\"' > /etc/default/grub.d/ehci_hcd.conf"
				echo '    update-grub'
				echo 'Other distributions:'
				echo "    sed -i '/^GRUB_CMDLINE_LINUX/s/\"\$/ initcall_blacklist=ehci_pci_init,ehci_hcd_init\"/' /etc/default/grub'"
				echo '    grub-mkconfig -o /boot/grub/grub.cfg || grub2-mkconfig -o /boot/grub2/grub.cfg'
				echo 'Or using grubby (if installed)':
				echo "    grubby --args 'initcall_blacklist=ehci_pci_init,ehci_hcd_init' --update-kernel DEFAULT"
				echo 'Finally, reboot the machine for this to take effect'
				rc=1
				;;
		esac
	fi
done
IFS=$oldifs
if [ "$rc" -eq 0 ]; then
  echo "No IRQ conflicts found"
fi
exit "$rc"
