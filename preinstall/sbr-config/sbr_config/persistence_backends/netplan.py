"""Netplan YAML persistence backend."""

import glob
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
from .base import PersistenceBackend, group_by_name

logger = logging.getLogger(__name__)

# Netplan device sections an interface definition can live under. Adding
# an interface under the wrong section (e.g. a VLAN under ethernets)
# makes `netplan apply` reject the whole config.
NETPLAN_SECTIONS = ("ethernets", "vlans", "bonds", "bridges")


class NetplanBackend(PersistenceBackend):
    """Write Netplan YAML configuration for SBR persistence.

    Creates /etc/netplan/90-sbr-config.yaml. Netplan merges files in
    lexical order, and a later file's list value REPLACES an earlier
    file's entirely -- so this file must carry the union of any existing
    routes / routing-policy for the interfaces it touches, or applying it
    would delete the user's own static routes on those interfaces.
    """

    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
    ) -> List[str]:
        if not os.path.isdir(NETPLAN_DIR):
            os.makedirs(NETPLAN_DIR, exist_ok=True)

        table_num = {t.name: t.number for t in tables}
        groups = group_by_name(interfaces)
        existing = self._load_existing_config([name for name, _ in groups])

        content = self._generate_yaml(groups, table_num, existing)
        fpath = os.path.join(NETPLAN_DIR, NETPLAN_CONFIG_FILE)
        # 0600: netplan warns (newer versions error) on world-readable config
        write_file_atomic(fpath, content, mode=0o600)

        logger.info("Wrote netplan config: %s", fpath)

        # Apply netplan (can take a while -- it cycles interface config)
        run_command("netplan apply", check=False, timeout=60)

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
                run_command("netplan apply", check=False, timeout=60)
        return removed

    def describe(self) -> str:
        fpath = os.path.join(NETPLAN_DIR, NETPLAN_CONFIG_FILE)
        return (
            f"Netplan YAML config at {fpath}\n"
            f"Contains routing-policy rules for each SBR interface, merged "
            f"with any routes those interfaces already had in other files."
        )

    def _load_existing_config(self, iface_names: List[str]) -> Dict[str, dict]:
        """Learn each managed interface's device section and existing
        routes / routing-policy from the other netplan files.

        PyYAML is a dependency of netplan itself, so it is importable on
        any system where this backend runs; if it somehow isn't, fall
        back to no merge with a loud warning.
        """
        result = {
            name: {
                "section": "ethernets",
                "routes": [],
                "policy": [],
                "later_conflict": False,
                "defined": False,
            }
            for name in iface_names
        }
        try:
            import yaml
        except ImportError:
            logger.warning(
                "PyYAML unavailable; cannot merge existing netplan routes. "
                "Routes defined elsewhere for SBR-managed interfaces may be "
                "overridden by %s.", NETPLAN_CONFIG_FILE,
            )
            return result

        for path in sorted(glob.glob(os.path.join(NETPLAN_DIR, "*.yaml"))):
            basename = os.path.basename(path)
            if basename == NETPLAN_CONFIG_FILE:
                continue
            content = read_file(path)
            if not content:
                continue
            try:
                data = yaml.safe_load(content) or {}
            except yaml.YAMLError as e:
                logger.warning("Could not parse netplan file %s: %s", path, e)
                continue
            network = data.get("network") or {}
            if not isinstance(network, dict):
                continue

            sorts_after_ours = basename > NETPLAN_CONFIG_FILE
            for section in NETPLAN_SECTIONS:
                devices = network.get(section)
                if not isinstance(devices, dict):
                    continue
                for name, cfg in devices.items():
                    if name not in result or not isinstance(cfg, dict):
                        continue
                    result[name]["section"] = section
                    result[name]["defined"] = True
                    for yaml_key, dest in (("routes", "routes"),
                                           ("routing-policy", "policy")):
                        vals = cfg.get(yaml_key)
                        if not isinstance(vals, list):
                            continue
                        if sorts_after_ours:
                            # That file's list will override ours wholesale.
                            result[name]["later_conflict"] = True
                        else:
                            result[name][dest].extend(
                                v for v in vals if isinstance(v, dict)
                            )

        for name, info in result.items():
            if info["later_conflict"]:
                logger.warning(
                    "A netplan file sorting after %s defines routes or "
                    "routing-policy for %s; netplan will let it override "
                    "sbr-config's entries, so SBR persistence for this "
                    "interface may be incomplete.",
                    NETPLAN_CONFIG_FILE, name,
                )
        return result

    def _generate_yaml(
        self,
        groups: list,
        table_num: Dict[str, int],
        existing: Dict[str, dict],
    ) -> str:
        """Generate netplan YAML content.

        Written by hand (deterministic output, no dump-format surprises);
        existing route/policy entries from other files are re-emitted so
        our whole-list override preserves them.
        """
        header = [
            MANAGED_COMMENT,
            "# Source-based routing configuration for multi-NIC systems.",
            "# This file is merged with other netplan configs. Routes that",
            "# other files define for these interfaces are re-emitted here",
            "# because netplan replaces list values wholesale across files.",
            "",
            "network:",
            "  version: 2",
        ]

        by_section: Dict[str, List[str]] = {}
        for name, entries in groups:
            table_name = f"{TABLE_NAME_PREFIX}{name}"
            tnum = table_num.get(table_name)
            if tnum is None:
                continue

            info = existing.get(name) or {
                "section": "ethernets", "routes": [], "policy": [],
                "defined": False,
            }

            # Only emit entries for interfaces netplan already defines.
            # Emitting one for an unmanaged interface (e.g. a manually
            # created VLAN) makes netplan generate a .network for it, and
            # networkd then takes over the link with no address config --
            # stripping its addresses on apply.
            if not info.get("defined"):
                logger.warning(
                    "%s is not defined in any netplan file; skipping SBR "
                    "persistence for it (adding it would make networkd take "
                    "over the link and drop its address config). Runtime "
                    "config is active but will not survive a reboot.",
                    name,
                )
                continue

            # Follows the planner's allocation scheme; clamped so
            # pre-existing sbr_ tables numbered below 100 don't produce a
            # negative priority.
            priority = max(100, 100 + (tnum - 100) * 10)

            block = [f"    {name}:", "      routes:"]

            # Existing routes from other files first, verbatim
            emitted = set()
            for route in info["routes"]:
                block.extend(_emit_mapping_entry(route, indent="        "))
                emitted.add((str(route.get("to")), str(route.get("table"))))

            # Our SBR routes (skip any an existing entry already covers)
            seen_subnets = set()
            for entry in entries:
                if entry.subnet in seen_subnets:
                    continue
                seen_subnets.add(entry.subnet)
                if (entry.subnet, str(tnum)) in emitted:
                    continue
                block.extend([
                    f"        - to: {entry.subnet}",
                    f"          table: {tnum}",
                ])

            gateway = next(
                (e.gateway for e in entries if e.gateway is not None), None
            )
            if gateway is not None and ("default", str(tnum)) not in emitted:
                block.extend([
                    f"        - to: default",
                    f"          via: {gateway}",
                    f"          table: {tnum}",
                ])

            block.append("      routing-policy:")
            emitted_policy = set()
            for policy in info["policy"]:
                block.extend(_emit_mapping_entry(policy, indent="        "))
                emitted_policy.add(
                    (str(policy.get("from")), str(policy.get("table")))
                )
            for entry in entries:
                if (entry.ip_address, str(tnum)) in emitted_policy:
                    continue
                block.extend([
                    f"        - from: {entry.ip_address}",
                    f"          table: {tnum}",
                    f"          priority: {priority}",
                ])

            by_section.setdefault(info["section"], []).extend(block)

        lines = list(header)
        for section in NETPLAN_SECTIONS:
            if section in by_section:
                lines.append(f"  {section}:")
                lines.extend(by_section[section])

        lines.append("")
        return "\n".join(lines)


def _emit_mapping_entry(mapping: dict, indent: str) -> List[str]:
    """Re-serialize a flat YAML mapping as a list item, preserving keys."""
    lines = []
    first = True
    for key, value in mapping.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        prefix = f"{indent}- " if first else f"{indent}  "
        lines.append(f"{prefix}{key}: {rendered}")
        first = False
    return lines
