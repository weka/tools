"""systemd-networkd drop-in persistence backend."""

import glob
import logging
import os
from typing import List, Optional

from ..constants import (
    MANAGED_COMMENT,
    NETWORKD_DROPIN_NAME,
    NETWORKD_LINKS_STATE_DIR,
    SYSTEMD_NETWORK_DIR,
    TABLE_NAME_PREFIX,
)
from ..models import InterfaceInfo, PlannedChange, RoutingTable
from ..utils import read_file, run_command, write_file_atomic
from .base import PersistenceBackend, group_by_name, rule_priority_for

logger = logging.getLogger(__name__)


class SystemdNetworkdBackend(PersistenceBackend):
    """Write systemd-networkd drop-in configs for SBR persistence.

    networkd applies exactly ONE .network file per link -- the first
    match in lexical order; all later matches are ignored
    (systemd.network(5)). A standalone SBR .network file therefore either
    shadows the file that actually configures the link (stripping its
    address management, since KeepConfiguration defaults to off) or is
    silently ignored. SBR settings must instead go into a drop-in,
    <applied-file>.network.d/50-sbr.conf, which merges into whichever
    file networkd already applies to the link.
    """

    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
        rule_priorities=None,
    ) -> List[str]:
        table_num = {t.name: t.number for t in tables}

        # Versions <=1.2.x wrote dangerous standalone 50-sbr-*.network
        # files (see class docstring); shed them before writing drop-ins.
        removed_legacy = self._remove_legacy_files()

        written = []
        skipped = []
        for name, entries in group_by_name(interfaces):
            table_name = f"{TABLE_NAME_PREFIX}{name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            network_file = self._applied_network_file(name)
            if network_file is None:
                skipped.append(name)
                logger.warning(
                    "%s has no systemd-networkd .network file applied to it "
                    "(unmanaged by networkd); skipping SBR persistence for "
                    "this interface. Runtime config is active but will not "
                    "survive a reboot.",
                    name,
                )
                continue

            dropin_dir = os.path.join(
                SYSTEMD_NETWORK_DIR, os.path.basename(network_file) + ".d"
            )
            os.makedirs(dropin_dir, exist_ok=True)
            fpath = os.path.join(dropin_dir, NETWORKD_DROPIN_NAME)
            write_file_atomic(
                fpath,
                self._generate_dropin(name, entries, tnum, rule_priorities),
            )
            written.append(fpath)
            logger.info("Wrote networkd drop-in: %s", fpath)

        if written or removed_legacy:
            run_command("networkctl reload", check=False, timeout=30)

        return written

    def remove_config(self) -> List[str]:
        removed = []

        for fpath in glob.glob(
            os.path.join(SYSTEMD_NETWORK_DIR, "*.network.d", NETWORKD_DROPIN_NAME)
        ):
            content = read_file(fpath)
            if content and MANAGED_COMMENT in content:
                os.unlink(fpath)
                removed.append(fpath)
                logger.info("Removed networkd drop-in: %s", fpath)
                try:
                    os.rmdir(os.path.dirname(fpath))
                except OSError:
                    pass  # not empty

        removed += self._remove_legacy_files()

        if removed:
            run_command("networkctl reload", check=False, timeout=30)

        return removed

    def describe(self) -> str:
        return (
            f"systemd-networkd drop-ins: "
            f"{SYSTEMD_NETWORK_DIR}/<applied-file>.network.d/{NETWORKD_DROPIN_NAME}\n"
            f"Merged into the .network file networkd already applies to each link."
        )

    def _remove_legacy_files(self) -> List[str]:
        """Remove standalone 50-sbr-*.network files written by <=1.2.x."""
        removed = []
        if not os.path.isdir(SYSTEMD_NETWORK_DIR):
            return removed
        for fname in os.listdir(SYSTEMD_NETWORK_DIR):
            if not (fname.startswith("50-sbr-") and fname.endswith(".network")):
                continue
            fpath = os.path.join(SYSTEMD_NETWORK_DIR, fname)
            content = read_file(fpath)
            if content and MANAGED_COMMENT in content:
                os.unlink(fpath)
                removed.append(fpath)
                logger.info(
                    "Removed legacy standalone networkd file %s (could shadow "
                    "or be shadowed by the link's real .network file)",
                    fpath,
                )
        return removed

    def _applied_network_file(self, name: str) -> Optional[str]:
        """Find the .network file networkd currently applies to a link.

        Read from networkd's runtime state (NETWORK_FILE= in
        /run/systemd/netif/links/<ifindex>); returns None when networkd
        doesn't manage the link.
        """
        try:
            with open("/sys/class/net/{}/ifindex".format(name)) as f:
                ifindex = f.read().strip()
        except OSError:
            return None
        state = read_file(os.path.join(NETWORKD_LINKS_STATE_DIR, ifindex))
        if not state:
            return None
        for line in state.splitlines():
            if line.startswith("NETWORK_FILE="):
                return line.split("=", 1)[1].strip() or None
        return None

    def _generate_dropin(
        self,
        name: str,
        entries: List[InterfaceInfo],
        table_number: int,
        rule_priorities=None,
    ) -> str:
        """Generate drop-in content: routes and policy rules only.

        No [Match] section -- the drop-in merges into the .network file
        that already matches the link.
        """
        ips = ", ".join(e.ip_address for e in entries)
        lines = [
            MANAGED_COMMENT,
            f"# Source-based routing for {name} ({ips})",
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
            priority = rule_priority_for(
                entry.ip_address, table_number, rule_priorities
            )
            lines.extend([
                "[RoutingPolicyRule]",
                f"From={entry.ip_address}",
                f"Table={table_number}",
                f"Priority={priority}",
                "",
            ])

        return "\n".join(lines)
