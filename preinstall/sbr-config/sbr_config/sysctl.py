"""Validate and configure kernel sysctl parameters for source-based routing."""

import logging
import os
from typing import Dict, List, Tuple

from .constants import (
    MANAGED_COMMENT,
    SYSCTL_CONF_PATH,
    SYSCTL_PER_IFACE_TEMPLATE,
    SYSCTL_SETTINGS,
)
from .exceptions import ConfigurationError
from .models import ChangeType, PlannedChange, SysctlSetting, ValidationResult
from .utils import read_file, run_command, write_file_atomic

logger = logging.getLogger(__name__)


def read_sysctl(key: str) -> str:
    """Read a sysctl value from /proc/sys.

    Args:
        key: Sysctl key in dotted notation (e.g., net.ipv4.conf.all.rp_filter).

    Returns:
        The current value as a string, or "unknown" if unreadable.
    """
    proc_path = "/proc/sys/" + key.replace(".", "/")
    try:
        with open(proc_path, "r") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError) as e:
        logger.warning("Cannot read sysctl %s: %s", key, e)
        return "unknown"


def read_all_sysctl_values(interface_names: List[str]) -> Dict[str, str]:
    """Read all SBR-relevant sysctl values.

    Args:
        interface_names: List of interface names to check per-interface settings.

    Returns:
        Dict mapping sysctl keys to their current values.
    """
    values = {}

    # Global settings
    for key in SYSCTL_SETTINGS:
        values[key] = read_sysctl(key)

    # Per-interface rp_filter
    for iface in interface_names:
        key = SYSCTL_PER_IFACE_TEMPLATE.format(iface=iface)
        values[key] = read_sysctl(key)

    return values


def validate_sysctl(
    current_values: Dict[str, str],
    interface_names: List[str],
) -> List[ValidationResult]:
    """Validate sysctl settings against SBR requirements.

    Args:
        current_values: Dict of sysctl key -> current value.
        interface_names: Non-default interface names to check.

    Returns:
        List of ValidationResult for each sysctl check.
    """
    results = []

    # Check global settings
    for key, spec in SYSCTL_SETTINGS.items():
        current = current_values.get(key, "unknown")
        results.append(ValidationResult(
            interface_name="(global)",
            check_name=f"sysctl {key}",
            is_correct=(current == spec["required"]),
            current_value=f"{current} ({_describe_rp_filter(current) if 'rp_filter' in key else current})",
            expected_value=f"{spec['required']} ({spec['description']})",
            fix_description=spec["reason"] if current != spec["required"] else "",
        ))

    # Check per-interface rp_filter
    for iface in interface_names:
        key = SYSCTL_PER_IFACE_TEMPLATE.format(iface=iface)
        current = current_values.get(key, "unknown")
        required = "2"
        results.append(ValidationResult(
            interface_name=iface,
            check_name=f"sysctl {key}",
            is_correct=(current == required),
            current_value=f"{current} ({_describe_rp_filter(current)})",
            expected_value=f"{required} (loose mode)",
            fix_description=(
                f"Per-interface rp_filter for {iface} must be set to loose mode (2). "
                f"The kernel uses max(all, iface) so both the global and per-interface "
                f"settings must be 2 for loose mode to take effect."
            ) if current != required else "",
        ))

    return results


def plan_sysctl_changes(
    current_values: Dict[str, str],
    interface_names: List[str],
) -> List[PlannedChange]:
    """Generate PlannedChange entries for sysctl settings that need updating.

    Args:
        current_values: Dict of sysctl key -> current value.
        interface_names: Non-default interface names.

    Returns:
        List of PlannedChange for sysctl modifications.
    """
    changes = []

    # Global settings
    for key, spec in SYSCTL_SETTINGS.items():
        current = current_values.get(key, "unknown")
        if current != spec["required"]:
            changes.append(PlannedChange(
                change_type=ChangeType.SET_SYSCTL,
                description=f"Set {key} = {spec['required']}",
                reason=spec["reason"],
                command=f"sysctl -w {key}={spec['required']}",
                rollback_command=f"sysctl -w {key}={current}" if current != "unknown" else None,
            ))

    # Per-interface rp_filter
    for iface in interface_names:
        key = SYSCTL_PER_IFACE_TEMPLATE.format(iface=iface)
        current = current_values.get(key, "unknown")
        required = "2"
        if current != required:
            changes.append(PlannedChange(
                change_type=ChangeType.SET_SYSCTL,
                description=f"Set {key} = {required}",
                reason=(
                    f"Per-interface rp_filter for {iface} must be loose mode (2) "
                    f"so that packets arriving on {iface} are not dropped by the "
                    f"reverse path filter when the main table doesn't have a matching route."
                ),
                command=f"sysctl -w {key}={required}",
                interface=iface,
                rollback_command=f"sysctl -w {key}={current}" if current != "unknown" else None,
            ))

    return changes


def apply_sysctl(key: str, value: str) -> None:
    """Apply a single sysctl setting at runtime.

    Args:
        key: Sysctl key in dotted notation.
        value: Value to set.
    """
    run_command(f"sysctl -w {key}={value}")
    logger.info("Set sysctl %s = %s", key, value)


def write_sysctl_persistence(
    changes: List[PlannedChange],
) -> str:
    """Write /etc/sysctl.d/90-sbr-config.conf for persistence.

    Args:
        changes: List of sysctl PlannedChange entries.

    Returns:
        Path to the written config file.
    """
    sysctl_changes = [c for c in changes if c.change_type == ChangeType.SET_SYSCTL]
    if not sysctl_changes:
        return ""

    lines = [
        MANAGED_COMMENT,
        "# Sysctl settings for source-based routing",
        "#",
        "# These settings ensure multi-NIC systems correctly handle",
        "# reverse path filtering and ARP for source-based routing.",
        "",
    ]

    for change in sysctl_changes:
        # Extract key=value from the command "sysctl -w key=value"
        kv = change.command.replace("sysctl -w ", "")
        lines.append(f"# {change.description}")
        lines.append(kv)
        lines.append("")

    content = "\n".join(lines) + "\n"
    write_file_atomic(SYSCTL_CONF_PATH, content)
    logger.info("Wrote sysctl persistence config to %s", SYSCTL_CONF_PATH)
    return SYSCTL_CONF_PATH


def remove_sysctl_persistence() -> bool:
    """Remove the sbr-config sysctl.d file if it exists.

    Returns:
        True if a file was removed.
    """
    if os.path.exists(SYSCTL_CONF_PATH):
        # Verify it's ours before removing
        content = read_file(SYSCTL_CONF_PATH)
        if content and MANAGED_COMMENT in content:
            os.unlink(SYSCTL_CONF_PATH)
            logger.info("Removed sysctl persistence config %s", SYSCTL_CONF_PATH)
            return True
        else:
            logger.warning(
                "%s exists but doesn't appear to be managed by sbr-config; skipping removal",
                SYSCTL_CONF_PATH,
            )
    return False


def _describe_rp_filter(value: str) -> str:
    """Human-readable description of rp_filter value."""
    return {
        "0": "disabled",
        "1": "strict mode",
        "2": "loose mode",
    }.get(value, f"value={value}")
