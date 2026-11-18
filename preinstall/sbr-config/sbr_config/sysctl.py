"""Validate and configure kernel sysctl parameters for source-based routing."""

import logging
import os
import re
from typing import Dict, List, Optional, Tuple

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


def _read_proc_value(proc_path: str) -> str:
    """Read a /proc/sys value, returning 'unknown' if unreadable."""
    try:
        with open(proc_path, "r") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError) as e:
        logger.warning("Cannot read %s: %s", proc_path, e)
        return "unknown"


def read_sysctl(key: str) -> str:
    """Read a global sysctl value from /proc/sys.

    Args:
        key: Sysctl key in dotted notation (e.g., net.ipv4.conf.all.rp_filter).
             Only safe for keys whose segments contain no dots -- for
             per-interface keys use sysctl_key_to_cmd/_read_proc_value with
             an explicit path, since interface names may contain dots
             (VLANs like eth0.100).

    Returns:
        The current value as a string, or "unknown" if unreadable.
    """
    return _read_proc_value("/proc/sys/" + key.replace(".", "/"))


def sysctl_key_to_cmd(key: str) -> str:
    """Return a sysctl(8)-safe form of a dotted key.

    Per-interface rp_filter keys are rewritten to slash notation
    (net/ipv4/conf/<iface>/rp_filter) so interface names containing dots
    (VLANs like eth0.100) aren't split into bogus path components by the
    sysctl binary. Global keys pass through unchanged.
    """
    m = re.match(r"^net\.ipv4\.conf\.(.+)\.rp_filter$", key)
    if m and m.group(1) not in ("all", "default"):
        return "net/ipv4/conf/{}/rp_filter".format(m.group(1))
    return key


def _rp_filter_effectively_loose(current: str, all_rp: str) -> bool:
    """The kernel evaluates max(conf.all, conf.iface) for rp_filter, so
    loose mode is effective when EITHER value is 2. Single source of truth
    for both validation and planning -- they must stay in agreement.
    """
    return current == "2" or all_rp == "2"


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

    # Per-interface rp_filter. Read via an explicit /proc path -- the
    # dotted-key path building in read_sysctl would mangle interface
    # names that contain dots (VLANs).
    for iface in interface_names:
        key = SYSCTL_PER_IFACE_TEMPLATE.format(iface=iface)
        values[key] = _read_proc_value(
            "/proc/sys/net/ipv4/conf/{}/rp_filter".format(iface)
        )

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

    # Check per-interface rp_filter. The kernel uses max(all, iface), so
    # loose mode is effective when EITHER is 2 -- interfaces created after
    # boot inherit conf.default and conf.all=2 covers the rest. Requiring
    # iface==2 outright would false-fail after every reboot on interfaces
    # created before sysctl.d is applied.
    all_rp = current_values.get("net.ipv4.conf.all.rp_filter", "unknown")
    for iface in interface_names:
        key = SYSCTL_PER_IFACE_TEMPLATE.format(iface=iface)
        current = current_values.get(key, "unknown")
        required = "2"
        is_correct = _rp_filter_effectively_loose(current, all_rp)
        results.append(ValidationResult(
            interface_name=iface,
            check_name=f"sysctl {key}",
            is_correct=is_correct,
            current_value=(
                f"{current} ({_describe_rp_filter(current)})"
                + (" -- loose via conf.all" if is_correct and current != required else "")
            ),
            expected_value=f"{required} (loose mode, directly or via conf.all)",
            fix_description=(
                f"rp_filter must be loose (2) in effect for {iface}. The kernel "
                f"uses max(all, {iface}), so either the per-interface or the "
                f"global 'all' setting must be 2."
            ) if not is_correct else "",
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

    # Per-interface rp_filter: only needed when neither the interface nor
    # conf.all is already loose (kernel uses max of the two). Runtime-only --
    # these keys are deliberately never persisted to sysctl.d (see
    # write_sysctl_persistence).
    all_rp = current_values.get("net.ipv4.conf.all.rp_filter", "unknown")
    for iface in interface_names:
        key = SYSCTL_PER_IFACE_TEMPLATE.format(iface=iface)
        current = current_values.get(key, "unknown")
        required = "2"
        if not _rp_filter_effectively_loose(current, all_rp):
            # Slash notation keeps dotted interface names (VLANs) intact
            # when the sysctl binary parses the key.
            cmd_key = sysctl_key_to_cmd(key)
            changes.append(PlannedChange(
                change_type=ChangeType.SET_SYSCTL,
                description=f"Set {key} = {required}",
                reason=(
                    f"Per-interface rp_filter for {iface} must be loose mode (2) "
                    f"so that packets arriving on {iface} are not dropped by the "
                    f"reverse path filter when the main table doesn't have a matching route."
                ),
                command=f"sysctl -w {cmd_key}={required}",
                interface=iface,
                rollback_command=f"sysctl -w {cmd_key}={current}" if current != "unknown" else None,
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


def write_sysctl_persistence() -> str:
    """Write /etc/sysctl.d/90-sbr-config.conf for persistence.

    The file contains the COMPLETE set of required global SBR sysctl
    settings, not just the ones changed in this run. A setting that
    already happened to be correct at runtime (e.g. set manually with
    `sysctl -w`) still needs to be persisted or it reverts on reboot.

    Per-interface keys (net.ipv4.conf.<iface>.rp_filter) are deliberately
    NOT written here. sysctl.d is applied early at boot, before late-binding
    drivers (notably Mellanox/IPoIB ib*) create their interfaces, so those
    keys fail with "No such file or directory" on every boot -- and always
    fail on machines cloned from an image that had different NICs. They are
    also unnecessary: conf.default.rp_filter=2 is inherited by interfaces
    created after it is set, and the kernel evaluates max(all, iface), so
    conf.all.rp_filter=2 makes loose mode effective regardless.

    Returns:
        Path to the written config file.
    """
    write_file_atomic(SYSCTL_CONF_PATH, _sysctl_persistence_content())
    logger.info("Wrote sysctl persistence config to %s", SYSCTL_CONF_PATH)
    return SYSCTL_CONF_PATH


def _sysctl_persistence_content() -> str:
    """Build the exact desired content of the sysctl.d file.

    Deterministic on purpose: staleness detection compares the on-disk
    file against this output, which heals any drift (per-interface keys
    from <=1.2.0, delta-style files from 1.1.x, future format changes)
    without format-specific sniffing.
    """
    lines = [
        MANAGED_COMMENT,
        "# Sysctl settings for source-based routing",
        "#",
        "# These settings ensure multi-NIC systems correctly handle",
        "# reverse path filtering and ARP for source-based routing.",
        "#",
        "# Per-interface keys are intentionally absent: they break at boot",
        "# for interfaces that don't exist yet (e.g. ib* created by late",
        "# driver load). conf.default covers new interfaces and the kernel",
        "# uses max(all, iface) for rp_filter, so 'all' = 2 is sufficient.",
        "",
    ]

    for key, spec in SYSCTL_SETTINGS.items():
        lines.append(f"# {spec['description']}")
        lines.append(f"{key} = {spec['required']}")
        lines.append("")

    return "\n".join(lines) + "\n"


def refresh_sysctl_persistence(ensure: bool = False) -> Optional[str]:
    """Bring the managed sysctl.d file in line with the desired content.

    Staleness is "managed file differs from what write_sysctl_persistence
    would write" -- covering per-interface keys from <=1.2.0 (which fail
    at boot for interfaces created by late driver load, e.g. ib*),
    delta-style files from 1.1.x, and any future format drift. A file
    without our marker is never touched.

    Args:
        ensure: Also create the file when it doesn't exist (used on clean
                --configure runs where SBR is active but persistence is
                missing, so sysctls don't silently revert on reboot).

    Returns:
        "created", "rewritten", or None if nothing was done.
    """
    current = read_file(SYSCTL_CONF_PATH)
    if current is None:
        if not ensure:
            return None
        write_sysctl_persistence()
        return "created"
    if MANAGED_COMMENT not in current:
        logger.warning(
            "%s exists but is not managed by sbr-config; leaving it alone",
            SYSCTL_CONF_PATH,
        )
        return None
    if current == _sysctl_persistence_content():
        return None
    write_sysctl_persistence()
    logger.info("Rewrote stale %s (old or drifted format)", SYSCTL_CONF_PATH)
    return "rewritten"


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
