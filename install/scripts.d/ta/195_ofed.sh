#!/usr/bin/env bash

DESCRIPTION="Check if Mellanox OFED is installed"
SCRIPT_TYPE="parallel"

# fail immediately if no OFED installed
if ! ofed_info -n &> /dev/null; then
    echo "OFED not installed"
    exit 254
fi

# is it a supported OFED version?
OFEDVER=$(ofed_info -n)

case "$OFEDVER" in 
    5.1-2.5.8.0 | 5.1-2.6.2.0 | 5.4-3.4.0.0 | 5.4-3.5.8.0 | 5.6-1.0.3.3 | 5.6-2.0.9.0 | 5.7-1.0.2.0 | 5.8-1.1.2.1 | 5.8-3.0.7.0 | 5.9-0.5.6.0 | 23.04-1.1.3.0 | 23.10-0.5.5.0 )
        #continue
        ;;
    *)
        echo "Unsupported OFED version $OFEDVER"
        exit 254
        ;;
esac

#
# check the loaded modules. Correct OFED might be installed, but not running (kernel mismatch, for example)
#
if modinfo mlx5_core &> /dev/null; then
    MLX5_VER=$(modinfo mlx5_core | awk '/^version:/{ print $2 }')
else
    echo "No mlx5_core kernel module loaded"
    exit 254
fi

# make sure loaded drivers match the installed OFED
if [[ -n "$MLX5_VER" ]]; then
    if [[ "$MLX5_VER" != "${OFEDVER:0:9}" ]]; then
        echo "Loaded Mellanox driver $MLX5_VER does not match OFED version $OFEDVER!"
        exit 254
    fi
fi

echo "Valid OFED configuration observed"
exit 0
