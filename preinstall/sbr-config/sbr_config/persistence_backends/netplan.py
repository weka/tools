"""Netplan YAML persistence backend."""

import logging
import os
from typing import Dict, List

from ..constants import (
    MANAGED_COMMENT,
    NETPLAN_CONFIG_FILE,
    NETPLAN_DIR,
    TABLE_NAME_PREFIX,
)
from ..models import InterfaceInfo, PlannedChange, RoutingTable
from ..utils import read_file, run_command, write_file_atomic
from .base import PersistenceBackend

logger = logging.getLogger(__name__)


class NetplanBackend(PersistenceBackend):
    """Write Netplan YAML configuration for SBR persistence.

    Creates /etc/netplan/90-sbr-config.yaml with routing-policy
    sections for each interface.
    """

    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
    ) -> List[str]:
        if not os.path.isdir(NETPLAN_DIR):
            os.makedirs(NETPLAN_DIR, exist_ok=True)

        # Build table name->number mapping
        table_num = {t.name: t.number for t in tables}

        content = self._generate_yaml(interfaces, table_num)
        fpath = os.path.join(NETPLAN_DIR, NETPLAN_CONFIG_FILE)
        write_file_atomic(fpath, content)

        logger.info("Wrote netplan config: %s", fpath)

        # Apply netplan
        run_command("netplan apply", check=False)

        return [fpath]

    def remove_config(self) -> List[str]:
        fpath = os.path.join(NETPLAN_DIR, NETPLAN_CONFIG_FILE)
        removed = []
        if os.path.exists(fpath):
            content = read_file(fpath)
            if content and MANAGED_COMMENT in content:
                os.unlink(fpath)
                removed.append(fpath)
                logger.info("Removed netplan config: %s", fpath)
                run_command("netplan apply", check=False)
        return removed

    def describe(self) -> str:
        fpath = os.path.join(NETPLAN_DIR, NETPLAN_CONFIG_FILE)
        return (
            f"Netplan YAML config at {fpath}\n"
            f"Contains routing-policy rules for each SBR interface."
        )

    def _generate_yaml(
        self,
        interfaces: List[InterfaceInfo],
        table_num: Dict[str, int],
    ) -> str:
        """Generate netplan YAML content.

        We write YAML manually to avoid requiring PyYAML dependency.
        """
        lines = [
            MANAGED_COMMENT,
            "# Source-based routing configuration for multi-NIC systems.",
            "# This file is merged with other netplan configs.",
            "",
            "network:",
            "  version: 2",
            "  ethernets:",
        ]

        for iface in interfaces:
            table_name = f"{TABLE_NAME_PREFIX}{iface.name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            priority = 100 + (tnum - 100) * 10

            route_lines = [
                f"    {iface.name}:",
                f"      routes:",
                f"        - to: {iface.subnet}",
                f"          table: {tnum}",
            ]

            # Only add default route if a gateway is known
            if iface.gateway is not None:
                route_lines.extend([
                    f"        - to: default",
                    f"          via: {iface.gateway}",
                    f"          table: {tnum}",
                ])

            route_lines.extend([
                f"      routing-policy:",
                f"        - from: {iface.ip_address}",
                f"          table: {tnum}",
                f"          priority: {priority}",
            ])

            lines.extend(route_lines)

        lines.append("")
        return "\n".join(lines)
