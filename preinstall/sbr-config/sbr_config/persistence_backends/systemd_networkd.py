"""systemd-networkd .network file persistence backend."""

import logging
import os
from typing import List

from ..constants import MANAGED_COMMENT, SYSTEMD_NETWORK_DIR, TABLE_NAME_PREFIX
from ..models import InterfaceInfo, PlannedChange, RoutingTable
from ..utils import read_file, run_command, write_file_atomic
from .base import PersistenceBackend

logger = logging.getLogger(__name__)


class SystemdNetworkdBackend(PersistenceBackend):
    """Write systemd-networkd .network files for SBR persistence.

    Creates /etc/systemd/network/50-sbr-<iface>.network files with
    [Route] and [RoutingPolicyRule] sections.
    """

    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
    ) -> List[str]:
        if not os.path.isdir(SYSTEMD_NETWORK_DIR):
            os.makedirs(SYSTEMD_NETWORK_DIR, exist_ok=True)

        # Build table name->number mapping
        table_num = {t.name: t.number for t in tables}

        written = []
        for iface in interfaces:
            table_name = f"{TABLE_NAME_PREFIX}{iface.name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            content = self._generate_network_file(iface, tnum)
            fpath = os.path.join(SYSTEMD_NETWORK_DIR, f"50-sbr-{iface.name}.network")
            write_file_atomic(fpath, content)
            written.append(fpath)
            logger.info("Wrote networkd config: %s", fpath)

        # Reload networkd
        if written:
            run_command("networkctl reload", check=False)

        return written

    def remove_config(self) -> List[str]:
        removed = []
        if not os.path.isdir(SYSTEMD_NETWORK_DIR):
            return removed

        for fname in os.listdir(SYSTEMD_NETWORK_DIR):
            if fname.startswith("50-sbr-") and fname.endswith(".network"):
                fpath = os.path.join(SYSTEMD_NETWORK_DIR, fname)
                content = read_file(fpath)
                if content and MANAGED_COMMENT in content:
                    os.unlink(fpath)
                    removed.append(fpath)
                    logger.info("Removed networkd config: %s", fpath)

        if removed:
            run_command("networkctl reload", check=False)

        return removed

    def describe(self) -> str:
        return (
            f"systemd-networkd .network files in {SYSTEMD_NETWORK_DIR}/\n"
            f"Files named 50-sbr-<interface>.network with Route and RoutingPolicyRule sections."
        )

    def _generate_network_file(self, iface: InterfaceInfo, table_number: int) -> str:
        """Generate a .network file for a single interface."""
        # Determine priority (use same logic as planner)
        priority = 100 + (table_number - 100) * 10

        lines = [
            MANAGED_COMMENT,
            f"# Source-based routing for {iface.name} ({iface.ip_address})",
            "",
            "[Match]",
            f"Name={iface.name}",
            "",
            "[Route]",
            f"Destination={iface.subnet}",
            f"Table={table_number}",
            "",
        ]

        # Only add default route if a gateway is known
        if iface.gateway is not None:
            lines.extend([
                "[Route]",
                f"Gateway={iface.gateway}",
                f"Table={table_number}",
                "",
            ])

        lines.extend([
            "[RoutingPolicyRule]",
            f"From={iface.ip_address}",
            f"Table={table_number}",
            f"Priority={priority}",
            "",
        ])

        return "\n".join(lines)
