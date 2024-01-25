#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Check that all NVME devices have valid IRQ routing"
# script type is single, parallel, sequential, or parallel-compare-backends
SCRIPT_TYPE="parallel"
JIRA_REFERENCE=""
WTA_REFERENCE=""
KB_REFERENCE=""

RETURN_CODE=0


#Search all NVMe devices on the PCI bus, checking their IRQ 
#Look for lines similar to "Interrupt: pin A routed to IRQ -2147483648"
# a negative number indicates (likely) invalid IRQ routing
for PCI_DEVICE_ID in $(sudo lspci -mm | grep 'Non-Volatile memory controller' | awk '{print $1}') ; do
    INTERRUPT_LINE=$(sudo lspci -vv -s ${PCI_DEVICE_ID} | grep Interrupt: | grep -c -- -)
    if [[ ${INTERRUPT_LINE} -ge 1 ]]; then
        RETURN_CODE=254
        echo "The NVMe device at PCI address ${PCI_DEVICE_ID} appears to have"
        echo "invalid IRQ routing. This is indicated by the presence of a negative number in the"
        echo "\"Interrupt:\" line from lspci."
        echo "This might not cause a problem, but it might prevent an NVMe drive from being claimed"
        echo "by a Weka process."
        echo "This can be caused by the presence of an enabled APIC device. Review your hardware,"
        echo "firmware, and linux kernel settings if this is causing a problem"
    fi
done

exit ${RETURN_CODE}
