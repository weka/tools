"""Execute planned changes with atomic rollback on failure."""

import logging
from typing import List

from .constants import MANAGED_COMMENT, RT_TABLES_PATH
from .exceptions import ConfigurationError
from .models import ChangeType, PlannedChange
from .sysctl import apply_sysctl
from .utils import read_file, run_command, write_file_atomic

logger = logging.getLogger(__name__)


def apply_changes(changes: List[PlannedChange]) -> int:
    """Apply a list of planned changes to the system.

    Changes are applied in order. If any change fails, all previously
    applied changes are rolled back.

    Args:
        changes: Ordered list of PlannedChange to execute.

    Returns:
        Number of changes successfully applied.

    Raises:
        ConfigurationError: If a change fails and rollback completes.
    """
    if not changes:
        logger.info("No changes to apply")
        return 0

    applied: List[PlannedChange] = []

    try:
        for change in changes:
            logger.info("Applying: %s", change.description)
            _execute_change(change)
            applied.append(change)
            logger.info("Applied: %s", change.description)

    except Exception as e:
        logger.error("Failed at: %s -- %s", change.description, e)
        logger.info("Rolling back %d applied changes", len(applied))
        _rollback_applied(applied)
        raise ConfigurationError(
            f"Failed to apply: {change.description}\n"
            f"Error: {e}\n"
            f"Rolled back {len(applied)} previously applied changes."
        ) from e

    logger.info("Successfully applied %d changes", len(applied))
    return len(applied)


def _execute_change(change: PlannedChange) -> None:
    """Execute a single planned change."""
    if change.change_type == ChangeType.ADD_RT_TABLE:
        _add_rt_table_entry(change)
    elif change.change_type == ChangeType.SET_SYSCTL:
        # Extract key=value from "sysctl -w key=value"
        kv = change.command.replace("sysctl -w ", "")
        key, value = kv.split("=", 1)
        apply_sysctl(key, value)
    elif change.change_type in (
        ChangeType.ADD_ROUTE,
        ChangeType.ADD_RULE,
        ChangeType.DEL_ROUTE,
        ChangeType.DEL_RULE,
    ):
        run_command(change.command)
    else:
        raise ConfigurationError(f"Unknown change type: {change.change_type}")


def _add_rt_table_entry(change: PlannedChange) -> None:
    """Append a routing table entry to /etc/iproute2/rt_tables.

    Uses atomic write to prevent file corruption.
    """
    content = read_file(RT_TABLES_PATH) or ""

    # Extract "NUMBER NAME" from the echo command
    # Command format: echo 'NUMBER NAME' >> /etc/iproute2/rt_tables
    import re
    m = re.search(r"echo\s+'(\d+\s+\S+)'", change.command)
    if not m:
        raise ConfigurationError(
            f"Cannot parse rt_table entry from command: {change.command}"
        )
    entry = m.group(1)

    # Check if already present (idempotent)
    if entry in content:
        logger.info("rt_tables entry already present: %s", entry)
        return

    # Ensure the file ends with a newline before appending
    if content and not content.endswith("\n"):
        content += "\n"

    # Add our marker if not present
    if MANAGED_COMMENT not in content:
        content += f"\n{MANAGED_COMMENT}\n"

    content += f"{entry}\n"
    write_file_atomic(RT_TABLES_PATH, content)
    logger.info("Added rt_tables entry: %s", entry)


def _rollback_applied(applied: List[PlannedChange]) -> None:
    """Roll back previously applied changes in reverse order.

    Errors during rollback are logged but don't propagate -- we want
    to attempt rolling back as much as possible.
    """
    for change in reversed(applied):
        if change.change_type == ChangeType.ADD_RT_TABLE:
            # rt_tables rollback is handled by file restore in rollback.py
            # For immediate rollback, try to remove the line we added
            try:
                _remove_rt_table_entry(change)
            except Exception as e:
                logger.error("Rollback failed for rt_table: %s", e)
        elif change.change_type == ChangeType.SET_SYSCTL:
            if change.rollback_command:
                try:
                    run_command(change.rollback_command, check=False)
                except Exception as e:
                    logger.error("Rollback failed for sysctl: %s", e)
        elif change.rollback_command:
            try:
                run_command(change.rollback_command, check=False)
            except Exception as e:
                logger.error("Rollback failed: %s -- %s", change.rollback_command, e)
        else:
            logger.warning(
                "No rollback command for: %s", change.description
            )


def _remove_rt_table_entry(change: PlannedChange) -> None:
    """Remove a routing table entry that was just added."""
    import re
    m = re.search(r"echo\s+'(\d+\s+\S+)'", change.command)
    if not m:
        return

    entry = m.group(1)
    content = read_file(RT_TABLES_PATH) or ""
    lines = content.splitlines()
    new_lines = [line for line in lines if line.strip() != entry]

    # Also remove our marker if no sbr_ entries remain
    has_sbr = any("sbr_" in line for line in new_lines if not line.startswith("#"))
    if not has_sbr:
        new_lines = [line for line in new_lines if line.strip() != MANAGED_COMMENT]

    write_file_atomic(RT_TABLES_PATH, "\n".join(new_lines) + "\n")
