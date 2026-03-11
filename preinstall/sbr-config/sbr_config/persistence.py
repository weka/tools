"""Persistence dispatch: select and invoke the correct backend."""

import logging
from typing import List

from .constants import TABLE_NAME_PREFIX
from .exceptions import PersistenceError
from .models import (
    ChangeType,
    NetworkManagerType,
    PlannedChange,
    RoutingTable,
    SystemState,
)
from .persistence_backends.ifupdown import IfupdownBackend
from .persistence_backends.netplan import NetplanBackend
from .persistence_backends.networkmanager import NetworkManagerBackend
from .persistence_backends.systemd_networkd import SystemdNetworkdBackend
from .sysctl import write_sysctl_persistence

logger = logging.getLogger(__name__)


def write_persistence(
    state: SystemState,
    changes: List[PlannedChange],
) -> List[str]:
    """Write persistent configuration using the appropriate backend.

    Args:
        state: Current system state (includes network manager detection).
        changes: The planned changes that were applied.

    Returns:
        List of file paths that were written.

    Raises:
        PersistenceError: If persistence cannot be written.
    """
    files_written = []

    # Write sysctl persistence (common to all backends)
    sysctl_path = write_sysctl_persistence(changes)
    if sysctl_path:
        files_written.append(sysctl_path)

    # Build table list (include both existing and newly added)
    tables = list(state.routing_tables)
    for change in changes:
        if change.change_type == ChangeType.ADD_RT_TABLE:
            # Parse "echo 'NUM NAME' >> ..."
            import re
            m = re.search(r"echo\s+'(\d+)\s+(\S+)'", change.command)
            if m:
                tables.append(RoutingTable(number=int(m.group(1)), name=m.group(2)))

    table_names = {t.name for t in tables}

    # Identify ALL interfaces that should have SBR persistence.
    # This includes interfaces configured in previous runs whose
    # routing is already correct (i.e. no new changes), so that
    # the persistence file is always a COMPLETE representation of
    # the desired state -- not just the delta from this run.
    sbr_interfaces = []
    for iface in state.interfaces:
        if iface.is_loopback or iface.is_default_route_interface:
            continue
        if not iface.is_up:
            continue
        # Include if the interface has (or is getting) an sbr_ table
        expected_table = TABLE_NAME_PREFIX + iface.name
        if expected_table in table_names:
            sbr_interfaces.append(iface)

    if not sbr_interfaces:
        logger.info("No interface-level persistence needed")
        return files_written

    # Select backend
    backend = _select_backend(state.network_manager)

    if backend is None:
        raise PersistenceError(
            f"No persistence backend available for network manager: "
            f"{state.network_manager.value}. "
            f"Runtime changes are active but will not survive reboot. "
            f"Consider creating a systemd service or cron @reboot job manually."
        )

    logger.info("Using persistence backend: %s", backend.describe())
    backend_files = backend.write_config(sbr_interfaces, tables, changes)
    files_written.extend(backend_files)

    return files_written


def _select_backend(nm_type: NetworkManagerType):
    """Select the appropriate persistence backend.

    Returns:
        A PersistenceBackend instance, or None if no backend available.
    """
    if nm_type == NetworkManagerType.NETWORKMANAGER:
        return NetworkManagerBackend()
    elif nm_type == NetworkManagerType.SYSTEMD_NETWORKD:
        return SystemdNetworkdBackend()
    elif nm_type == NetworkManagerType.IFUPDOWN:
        return IfupdownBackend()
    elif nm_type == NetworkManagerType.NETPLAN_NETWORKD:
        return NetplanBackend()
    elif nm_type == NetworkManagerType.NETPLAN_NM:
        # Netplan with NM renderer: use NM dispatcher as it's more reliable
        logger.info(
            "Netplan with NetworkManager renderer detected. "
            "Using NM dispatcher for persistence (more reliable than netplan routing-policy with NM)."
        )
        return NetworkManagerBackend()
    else:
        return None
