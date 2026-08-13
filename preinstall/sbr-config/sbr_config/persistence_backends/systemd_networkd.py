"""systemd-networkd .network file persistence backend."""

import logging
import os
from typing import List

from ..constants import MANAGED_COMMENT, SYSTEMD_NETWORK_DIR, TABLE_NAME_PREFIX
from ..models import InterfaceInfo, PlannedChange, RoutingTable
from ..utils import read_file, run_command, write_file_atomic
from .base import PersistenceBackend, group_by_name

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
        for name, entries in group_by_name(interfaces):
            table_name = f"{TABLE_NAME_PREFIX}{name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            content = self._generate_network_file(name, entries, tnum)
            fpath = os.path.join(SYSTEMD_NETWORK_DIR, f"50-sbr-{name}.network")
            write_file_atomic(fpath, content)
            written.append(fpath)
            logger.info("Wrote networkd config: %s", fpath)

        # Reload networkd
        if written:
            run_command("networkctl reload", check=False, timeout=30)

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
            run_command("networkctl reload", check=False, timeout=30)

        return removed

    def describe(self) -> str:
        return (
            f"systemd-networkd .network files in {SYSTEMD_NETWORK_DIR}/\n"
            f"Files named 50-sbr-<interface>.network with Route and RoutingPolicyRule sections."
        )

    def _generate_network_file(
        self,
        name: str,
        entries: List[InterfaceInfo],
        table_number: int,
    ) -> str:
        """Generate a .network file for a single interface.

        ``entries`` holds one InterfaceInfo per address on the interface.
        """
        # Follows the planner's allocation scheme; clamped so pre-existing
        # sbr_ tables numbered below 100 don't produce an invalid negative
        # priority.
        priority = max(100, 100 + (table_number - 100) * 10)

        ips = ", ".join(e.ip_address for e in entries)
        lines = [
            MANAGED_COMMENT,
            f"# Source-based routing for {name} ({ips})",
            "",
            "[Match]",
            f"Name={name}",
            "",
        ]

        seen_subnets = set()
        for entry in entries:
            if entry.subnet in seen_subnets:
                continue
            seen_subnets.add(entry.subnet)
            lines.extend([
                "[Route]",
                f"Destination={entry.subnet}",
                f"Table={table_number}",
                "",
            ])

        # Only add a default route if a gateway is known (one per table)
        gateway = next((e.gateway for e in entries if e.gateway is not None), None)
        if gateway is not None:
            lines.extend([
                "[Route]",
                f"Gateway={gateway}",
                f"Table={table_number}",
                "",
            ])

        for entry in entries:
            lines.extend([
                "[RoutingPolicyRule]",
                f"From={entry.ip_address}",
                f"Table={table_number}",
                f"Priority={priority}",
                "",
            ])

        return "\n".join(lines)
