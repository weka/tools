"""NetworkManager dispatcher script persistence backend."""

import logging
import os
from typing import List

from ..constants import (
    MANAGED_COMMENT,
    NM_DISPATCHER_DIR,
    NM_DISPATCHER_SCRIPT,
    TABLE_NAME_PREFIX,
)
from ..models import InterfaceInfo, PlannedChange, RoutingTable
from ..utils import command_exists, read_file, run_command, write_file_atomic
from .base import PersistenceBackend, group_by_name

logger = logging.getLogger(__name__)


class NetworkManagerBackend(PersistenceBackend):
    """Write a NetworkManager dispatcher script for SBR persistence.

    Creates /etc/NetworkManager/dispatcher.d/50-sbr-config which is
    called by NetworkManager when interfaces come up or go down.
    """

    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
    ) -> List[str]:
        script_path = os.path.join(NM_DISPATCHER_DIR, NM_DISPATCHER_SCRIPT)

        if not os.path.isdir(NM_DISPATCHER_DIR):
            os.makedirs(NM_DISPATCHER_DIR, exist_ok=True)

        # Build the dispatcher script
        script = self._generate_script(interfaces, tables, changes)
        write_file_atomic(script_path, script, mode=0o755)

        logger.info("Wrote NM dispatcher script: %s", script_path)

        # The dispatcher only fires for NM-managed devices. Hand-configured
        # storage NICs are often NM_CONTROLLED=no -- warn, or this
        # persistence silently does nothing for exactly those interfaces.
        self._warn_unmanaged(interfaces)

        return [script_path]

    def _warn_unmanaged(self, interfaces: List[InterfaceInfo]) -> None:
        if not command_exists("nmcli"):
            return
        for name, _ in group_by_name(interfaces):
            result = run_command(
                f"nmcli -t -f GENERAL.STATE device show {name}", check=False
            )
            if result.returncode == 0 and "unmanaged" in result.stdout:
                logger.warning(
                    "%s is unmanaged by NetworkManager; the dispatcher "
                    "script never fires for it, so SBR will not be restored "
                    "on link changes or reboot for this interface.",
                    name,
                )

    def remove_config(self) -> List[str]:
        script_path = os.path.join(NM_DISPATCHER_DIR, NM_DISPATCHER_SCRIPT)
        removed = []
        if os.path.exists(script_path):
            content = read_file(script_path)
            if content and MANAGED_COMMENT in content:
                os.unlink(script_path)
                removed.append(script_path)
                logger.info("Removed NM dispatcher script: %s", script_path)
        return removed

    def describe(self) -> str:
        script_path = os.path.join(NM_DISPATCHER_DIR, NM_DISPATCHER_SCRIPT)
        return (
            f"NetworkManager dispatcher script at {script_path}\n"
            f"Called automatically when interfaces come up/down."
        )

    def _generate_script(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
    ) -> str:
        """Generate the bash dispatcher script content.

        Commands are derived from the desired interface state (not from
        the delta of this run) so the script always contains the COMPLETE
        set of commands needed after a reboot.
        """
        table_num = {t.name: t.number for t in tables}

        lines = [
            "#!/bin/bash",
            MANAGED_COMMENT,
            "# NetworkManager dispatcher script for source-based routing.",
            "# Called with $1=interface_name $2=action (up/down)",
            "",
            'IFACE="$1"',
            'ACTION="$2"',
            "",
            'case "$IFACE" in',
        ]

        for name, entries in group_by_name(interfaces):
            table_name = f"{TABLE_NAME_PREFIX}{name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            # Derive the full command set from the desired state, covering
            # every address on the interface
            up_commands = []
            seen_subnets = set()
            for entry in entries:
                if entry.subnet in seen_subnets:
                    continue
                seen_subnets.add(entry.subnet)
                up_commands.append(
                    f"ip route replace {entry.subnet} dev {name} "
                    f"src {entry.ip_address} table {table_name}"
                )
            gateway = next((e.gateway for e in entries if e.gateway is not None), None)
            if gateway is not None:
                up_commands.append(
                    f"ip route replace default via {gateway} "
                    f"dev {name} table {table_name}"
                )
            for entry in entries:
                up_commands.append(
                    f"ip rule add from {entry.ip_address} table {table_name} 2>/dev/null"
                )

            down_commands = [
                f"ip rule del from {entry.ip_address} table {table_name}"
                for entry in entries
            ]
            down_commands.append(f"ip route flush table {table_name}")

            lines.append(f"    {name})")
            lines.append('        if [ "$ACTION" = "up" ]; then')
            for cmd in up_commands:
                lines.append(f"            {cmd}")
            lines.append('        elif [ "$ACTION" = "down" ]; then')
            for cmd in down_commands:
                lines.append(f"            {cmd} 2>/dev/null")
            lines.append("        fi")
            lines.append("        ;;")

        lines.append("esac")
        lines.append("")

        return "\n".join(lines)
