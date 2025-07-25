#!/bin/bash

set -ue # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Confirm every wekafs mount has the _netdev option"
SCRIPT_TYPE="parallel"

RETURN_CODE=0


if grep -P 'wekafs(?!.*_netdev)' -q /etc/fstab ; then
    echo "WARN: All wekafs mounts in /etc/fstab should use _netdev to avoid being mounted by systemd's local-fs.target"
    echo "Recommended resolution: add '_netdev' to the options for every wekafs and run 'systemctl daemon-reload'"
    RETURN_CODE=254
fi

if [[ ${RETURN_CODE} -eq 0 ]]; then
    echo "All wekafs mounts (if any) in /etc/fstab have the _netdev option"
fi

exit ${RETURN_CODE}
