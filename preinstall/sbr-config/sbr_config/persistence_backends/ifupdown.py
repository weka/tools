"""ifupdown (Debian/Ubuntu /etc/network/interfaces) persistence backend."""

import logging
import os
import re
from typing import List

from ..constants import (
    INTERFACES_D_DIR,
    INTERFACES_FILE,
    MANAGED_COMMENT,
    TABLE_NAME_PREFIX,
)
from ..models import InterfaceInfo, PlannedChange, RoutingTable
from ..utils import read_file, write_file_atomic
from .base import PersistenceBackend

logger = logging.getLogger(__name__)


class IfupdownBackend(PersistenceBackend):
    """Write ifupdown configuration for SBR persistence.

    Adds post-up/pre-down lines to interface stanzas in
    /etc/network/interfaces or creates drop-in files in
    /etc/network/interfaces.d/.
    """

    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
    ) -> List[str]:
        table_num = {t.name: t.number for t in tables}
        written = []

        for iface in interfaces:
            table_name = f"{TABLE_NAME_PREFIX}{iface.name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            # Derive the full command set from the desired state (not
            # just this run's delta) so persistence is always complete.
            up_cmds = [
                f"ip route replace {iface.subnet} dev {iface.name} "
                f"src {iface.ip_address} table {table_name}",
            ]
            if iface.gateway is not None:
                up_cmds.append(
                    f"ip route replace default via {iface.gateway} "
                    f"dev {iface.name} table {table_name}"
                )
            up_cmds.append(
                f"ip rule add from {iface.ip_address} table {table_name} 2>/dev/null"
            )

            down_cmds = [
                f"ip rule del from {iface.ip_address} table {table_name}",
                f"ip route flush table {table_name}",
            ]

            # Try to add to existing stanza in interfaces file
            if self._add_to_interfaces_file(iface.name, up_cmds, down_cmds):
                written.append(INTERFACES_FILE)
                continue

            # Fall back to drop-in file
            fpath = self._write_dropin(iface, up_cmds, down_cmds)
            if fpath:
                written.append(fpath)

        return written

    def remove_config(self) -> List[str]:
        removed = []

        # Remove from interfaces file
        if os.path.exists(INTERFACES_FILE):
            content = read_file(INTERFACES_FILE)
            if content and MANAGED_COMMENT in content:
                cleaned = self._remove_managed_lines(content)
                if cleaned != content:
                    write_file_atomic(INTERFACES_FILE, cleaned)
                    removed.append(INTERFACES_FILE)

        # Remove drop-in files
        if os.path.isdir(INTERFACES_D_DIR):
            for fname in os.listdir(INTERFACES_D_DIR):
                if fname.startswith("sbr-"):
                    fpath = os.path.join(INTERFACES_D_DIR, fname)
                    content = read_file(fpath)
                    if content and MANAGED_COMMENT in content:
                        os.unlink(fpath)
                        removed.append(fpath)

        return removed

    def describe(self) -> str:
        return (
            f"ifupdown configuration:\n"
            f"  post-up/pre-down lines in {INTERFACES_FILE}\n"
            f"  or drop-in files in {INTERFACES_D_DIR}/"
        )

    def _add_to_interfaces_file(
        self,
        iface_name: str,
        up_cmds: List[str],
        down_cmds: List[str],
    ) -> bool:
        """Try to add post-up/pre-down lines to an existing stanza.

        Returns True if successful, False if the stanza wasn't found.
        """
        content = read_file(INTERFACES_FILE)
        if not content:
            return False

        # Find the stanza for this interface
        pattern = rf'^(iface\s+{re.escape(iface_name)}\s+.*?)(?=\niface\s|\nauto\s|\nallow-|\n\Z|\Z)'
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if not match:
            return False

        stanza = match.group(0)
        stanza_end = match.end()

        # Build lines to insert
        insert_lines = [f"    {MANAGED_COMMENT}"]
        for cmd in up_cmds:
            insert_lines.append(f"    post-up {cmd}")
        for cmd in reversed(down_cmds):
            insert_lines.append(f"    pre-down {cmd} 2>/dev/null || true")
        insert_block = "\n".join(insert_lines)

        # Insert at end of stanza
        new_content = content[:stanza_end] + "\n" + insert_block + content[stanza_end:]
        write_file_atomic(INTERFACES_FILE, new_content)
        logger.info("Added SBR lines to %s stanza in %s", iface_name, INTERFACES_FILE)
        return True

    def _write_dropin(
        self,
        iface: InterfaceInfo,
        up_cmds: List[str],
        down_cmds: List[str],
    ) -> str:
        """Write a drop-in file in /etc/network/interfaces.d/."""
        if not os.path.isdir(INTERFACES_D_DIR):
            os.makedirs(INTERFACES_D_DIR, exist_ok=True)

        # Check that interfaces file sources the directory
        main_content = read_file(INTERFACES_FILE) or ""
        if "source" not in main_content and "interfaces.d" not in main_content:
            logger.warning(
                "%s does not source %s -- drop-in may not be loaded",
                INTERFACES_FILE,
                INTERFACES_D_DIR,
            )

        fpath = os.path.join(INTERFACES_D_DIR, f"sbr-{iface.name}")

        lines = [
            MANAGED_COMMENT,
            f"# Source-based routing for {iface.name} ({iface.ip_address})",
            "",
            f"auto {iface.name}",
            f"iface {iface.name} inet manual",
        ]
        for cmd in up_cmds:
            lines.append(f"    post-up {cmd}")
        for cmd in reversed(down_cmds):
            lines.append(f"    pre-down {cmd} 2>/dev/null || true")
        lines.append("")

        write_file_atomic(fpath, "\n".join(lines))
        logger.info("Wrote ifupdown drop-in: %s", fpath)
        return fpath

    def _remove_managed_lines(self, content: str) -> str:
        """Remove lines between MANAGED_COMMENT markers."""
        lines = content.splitlines()
        new_lines = []
        in_managed_block = False

        for line in lines:
            if MANAGED_COMMENT in line:
                in_managed_block = True
                continue
            if in_managed_block:
                # Lines in a managed block are indented post-up/pre-down
                if line.strip().startswith(("post-up", "pre-down")):
                    continue
                else:
                    in_managed_block = False
            new_lines.append(line)

        return "\n".join(new_lines)
