"""ifupdown (Debian/Ubuntu /etc/network/interfaces) persistence backend."""

import logging
import os
import re
from typing import List

from ..constants import (
    INTERFACES_D_DIR,
    INTERFACES_FILE,
    MANAGED_COMMENT,
    RULE_PRIORITY_INCREMENT,
    RULE_PRIORITY_START,
    TABLE_NAME_PREFIX,
    TABLE_NUMBER_START,
)
from ..models import InterfaceInfo, PlannedChange, RoutingTable
from ..utils import read_file, strip_managed_lines, write_file_atomic
from .base import PersistenceBackend, group_by_name

logger = logging.getLogger(__name__)


class IfupdownBackend(PersistenceBackend):
    """Write ifupdown configuration for SBR persistence.

    Adds post-up/pre-down lines to the interface's existing stanza --
    searching /etc/network/interfaces AND the files in
    /etc/network/interfaces.d/ (stanzas commonly live there via the
    default `source` line). Only when no stanza exists anywhere does it
    fall back to creating its own drop-in; a second stanza for an
    interface that already has one elsewhere would conflict with the
    original's method.
    """

    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
    ) -> List[str]:
        table_num = {t.name: t.number for t in tables}
        written = []

        # Strip managed lines from a previous run ONCE up front, so repeat
        # runs replace them instead of stacking duplicate (and possibly
        # stale) post-up/pre-down blocks. Done before the per-interface
        # loop -- stripping inside it would delete lines just written for
        # an earlier interface in this same run.
        for path in self._stanza_files():
            content = read_file(path)
            if content and MANAGED_COMMENT in content:
                write_file_atomic(path, strip_managed_lines(content))

        for name, entries in group_by_name(interfaces):
            table_name = f"{TABLE_NAME_PREFIX}{name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            # Derive the full command set from the desired state (not just
            # this run's delta) so persistence is always complete, covering
            # every address on the interface.
            up_cmds = []
            seen_subnets = set()
            for entry in entries:
                if entry.subnet in seen_subnets:
                    continue
                seen_subnets.add(entry.subnet)
                up_cmds.append(
                    f"ip route replace {entry.subnet} dev {name} "
                    f"src {entry.ip_address} table {table_name}"
                )
            gateway = next((e.gateway for e in entries if e.gateway is not None), None)
            if gateway is not None:
                up_cmds.append(
                    f"ip route replace default via {gateway} "
                    f"dev {name} table {table_name}"
                )
            # Explicit priority (planner's allocation scheme, clamped):
            # without it the kernel assigns its own, and the re-added rule
            # would land at a different precedence than the original.
            priority = max(
                RULE_PRIORITY_START,
                RULE_PRIORITY_START
                + (tnum - TABLE_NUMBER_START) * RULE_PRIORITY_INCREMENT,
            )
            for entry in entries:
                up_cmds.append(
                    f"ip rule add from {entry.ip_address} table {table_name} "
                    f"priority {priority} 2>/dev/null"
                )

            down_cmds = [
                f"ip rule del from {entry.ip_address} table {table_name}"
                for entry in entries
            ]
            down_cmds.append(f"ip route flush table {table_name}")

            # Add to the interface's existing stanza wherever it lives --
            # the main interfaces file or a sourced interfaces.d file
            stanza_path = None
            for path in self._stanza_files():
                if self._add_to_stanza_file(path, name, up_cmds, down_cmds):
                    stanza_path = path
                    break
            if stanza_path:
                written.append(stanza_path)
                continue

            # No stanza anywhere: fall back to our own drop-in file
            fpath = self._write_dropin(entries[0], up_cmds, down_cmds)
            if fpath:
                written.append(fpath)

        return written

    def _stanza_files(self) -> List[str]:
        """Files that may hold interface stanzas: the main interfaces
        file first, then sourced interfaces.d files (excluding our own
        sbr-* drop-ins, which are whole-file managed)."""
        paths = []
        if os.path.exists(INTERFACES_FILE):
            paths.append(INTERFACES_FILE)
        if os.path.isdir(INTERFACES_D_DIR):
            for fname in sorted(os.listdir(INTERFACES_D_DIR)):
                if fname.startswith("sbr-"):
                    continue
                fpath = os.path.join(INTERFACES_D_DIR, fname)
                if os.path.isfile(fpath):
                    paths.append(fpath)
        return paths

    def remove_config(self) -> List[str]:
        removed = []

        # Strip managed lines from stanza files (main + user drop-ins)
        for path in self._stanza_files():
            content = read_file(path)
            if content and MANAGED_COMMENT in content:
                cleaned = strip_managed_lines(content)
                if cleaned != content:
                    write_file_atomic(path, cleaned)
                    removed.append(path)

        # Remove our own drop-in files
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

    def _add_to_stanza_file(
        self,
        path: str,
        iface_name: str,
        up_cmds: List[str],
        down_cmds: List[str],
    ) -> bool:
        """Try to add post-up/pre-down lines to an existing stanza in path.

        Returns True if successful, False if the stanza wasn't found.
        """
        content = read_file(path)
        if not content:
            return False

        # Find the stanza for this interface
        pattern = rf'^(iface\s+{re.escape(iface_name)}\s+.*?)(?=\niface\s|\nauto\s|\nallow-|\n\Z|\Z)'
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if not match:
            return False

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
        write_file_atomic(path, new_content)
        logger.info("Added SBR lines to %s stanza in %s", iface_name, path)
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
