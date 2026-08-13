"""Save and restore system state for rollback capability."""

import glob
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from .constants import (
    BACKUP_DIR,
    INTERFACES_D_DIR,
    INTERFACES_FILE,
    MANAGED_COMMENT,
    NETPLAN_CONFIG_FILE,
    NETPLAN_DIR,
    NM_DISPATCHER_DIR,
    NM_DISPATCHER_SCRIPT,
    RT_TABLES_PATH,
    SYSCTL_CONF_PATH,
    SYSTEMD_NETWORK_DIR,
    TABLE_NAME_PREFIX,
)
from .exceptions import RollbackError
from .models import Route, Rule, SystemState
from .sysctl import remove_sysctl_persistence
from .utils import read_file, run_command, write_file_atomic

logger = logging.getLogger(__name__)

NM_DISPATCHER_PATH = os.path.join(NM_DISPATCHER_DIR, NM_DISPATCHER_SCRIPT)


def _managed_file_paths() -> List[str]:
    """All persistence file paths sbr-config manages (existing or not).

    Fixed paths are always listed; glob-based ones only when present.
    """
    paths = [
        SYSCTL_CONF_PATH,
        NM_DISPATCHER_PATH,
        os.path.join(NETPLAN_DIR, NETPLAN_CONFIG_FILE),
        INTERFACES_FILE,
    ]
    paths += sorted(glob.glob(os.path.join(SYSTEMD_NETWORK_DIR, "50-sbr-*.network")))
    paths += sorted(glob.glob(os.path.join(INTERFACES_D_DIR, "sbr-*")))
    return paths


def save_state(state: SystemState, backup_dir: str = BACKUP_DIR) -> str:
    """Serialize and save the current system state for later rollback.

    Args:
        state: The SystemState snapshot to save.
        backup_dir: Directory to store backup files.

    Returns:
        Path to the saved backup file.
    """
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(backup_dir, f"state_{timestamp}.json")

    # Never overwrite an existing backup -- add a counter suffix if two
    # saves land in the same second, so every backup stays referenceable.
    suffix = 1
    while os.path.exists(filepath):
        suffix += 1
        filepath = os.path.join(backup_dir, f"state_{timestamp}_{suffix}.json")

    data = state.to_dict()

    # Add raw file contents for exact restoration
    data["_raw_files"] = {
        RT_TABLES_PATH: state.rt_tables_file_content,
    }

    # Snapshot every managed persistence file (content, or None if absent)
    # so rollback can restore the box to this exact configuration instead
    # of stripping all SBR persistence.
    data["_persistence_files"] = {
        path: read_file(path) for path in _managed_file_paths()
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    # Create/update "latest" symlink
    latest = os.path.join(backup_dir, "latest.json")
    if os.path.islink(latest):
        os.unlink(latest)
    elif os.path.exists(latest):
        os.unlink(latest)
    os.symlink(filepath, latest)

    prune_backups(backup_dir)

    logger.info("Saved state backup to %s", filepath)
    return filepath


def rollback(
    backup_path: Optional[str] = None,
    backup_dir: str = BACKUP_DIR,
) -> None:
    """Restore the system to a previously saved state.

    The target is the running configuration captured in the backup: SBR
    rules, routes, rt_tables entries, and persistence files that existed
    at backup time are put back exactly; anything added since is removed.

    Args:
        backup_path: Specific backup file to restore from.
                     If None, uses the latest backup.
        backup_dir: Directory containing backups.

    Raises:
        RollbackError: If rollback fails.
    """
    if backup_path is None:
        backup_path = os.path.join(backup_dir, "latest.json")

    if not os.path.exists(backup_path):
        raise RollbackError(
            f"No backup found at {backup_path}. "
            f"Run 'sbr-config --configure' first to create a backup."
        )

    logger.info("Restoring from backup: %s", backup_path)

    try:
        with open(backup_path) as f:
            saved = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise RollbackError(f"Failed to read backup file: {e}") from e

    # Step 1: Remove current SBR rules and flush SBR tables so the restore
    # starts from a clean slate (uses the CURRENT rt_tables to find them)
    _remove_sbr_rules()
    _flush_sbr_tables()

    # Step 2: Restore /etc/iproute2/rt_tables
    _restore_rt_tables(saved)

    # Step 3: Re-add the SBR routes and rules that were running at backup time
    _restore_sbr_routes(saved)
    _restore_sbr_rules(saved)

    # Step 4: Restore sysctl settings
    _restore_sysctl(saved)

    # Step 5: Restore persistence configs to their backed-up contents
    _restore_persistence_files(saved)

    logger.info("Rollback complete")


def list_backups(backup_dir: str = BACKUP_DIR) -> List[dict]:
    """List available backup files with metadata.

    Returns:
        List of dicts with 'path', 'timestamp', 'is_latest' keys.
    """
    if not os.path.isdir(backup_dir):
        return []

    backups = []
    latest_target = None
    latest_link = os.path.join(backup_dir, "latest.json")
    if os.path.islink(latest_link):
        latest_target = os.path.realpath(latest_link)

    for fname in sorted(os.listdir(backup_dir)):
        if not fname.startswith("state_") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(backup_dir, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
            backups.append({
                "path": fpath,
                "timestamp": data.get("timestamp", "unknown"),
                "is_latest": os.path.realpath(fpath) == latest_target,
            })
        except Exception:
            backups.append({
                "path": fpath,
                "timestamp": "unreadable",
                "is_latest": False,
            })

    return backups


def prune_backups(
    backup_dir: str = BACKUP_DIR,
    keep: int = 10,
) -> int:
    """Remove old backups, keeping the most recent ones.

    Args:
        backup_dir: Directory containing backups.
        keep: Number of most recent backups to keep.

    Returns:
        Number of backups removed.
    """
    if not os.path.isdir(backup_dir):
        return 0

    files = sorted([
        f for f in os.listdir(backup_dir)
        if f.startswith("state_") and f.endswith(".json")
    ])

    if len(files) <= keep:
        return 0

    to_remove = files[:-keep]
    removed = 0
    for fname in to_remove:
        fpath = os.path.join(backup_dir, fname)
        try:
            os.unlink(fpath)
            removed += 1
            logger.debug("Pruned old backup: %s", fpath)
        except OSError as e:
            logger.warning("Failed to remove backup %s: %s", fpath, e)

    return removed


# ---------------------------------------------------------------------------
# Internal rollback steps
# ---------------------------------------------------------------------------

def _remove_sbr_rules() -> None:
    """Remove all IP rules that point to sbr_* tables."""
    result = run_command("ip rule show", check=False)
    for line in result.stdout.splitlines():
        if TABLE_NAME_PREFIX in line:
            # Extract the rule specification to delete it
            # Format: "100:  from 10.0.2.50 lookup sbr_eth1"
            parts = line.split(":", 1)
            if len(parts) == 2:
                rule_spec = parts[1].strip()
                # Replace "lookup" with "table" for the del command
                rule_spec = rule_spec.replace("lookup ", "table ")
                try:
                    run_command(f"ip rule del {rule_spec}", check=False)
                    logger.info("Removed rule: %s", rule_spec)
                except Exception as e:
                    logger.warning("Failed to remove rule '%s': %s", rule_spec, e)


def _flush_sbr_tables() -> None:
    """Flush routes from all sbr_* routing tables."""
    content = read_file(RT_TABLES_PATH) or ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].startswith(TABLE_NAME_PREFIX):
            table_name = parts[1]
            try:
                run_command(f"ip route flush table {table_name}", check=False)
                logger.info("Flushed table: %s", table_name)
            except Exception as e:
                logger.warning("Failed to flush table '%s': %s", table_name, e)


def _restore_rt_tables(saved: dict) -> None:
    """Restore /etc/iproute2/rt_tables from backup."""
    raw_files = saved.get("_raw_files", {})
    original_content = raw_files.get(RT_TABLES_PATH)

    if original_content is not None:
        write_file_atomic(RT_TABLES_PATH, original_content)
        logger.info("Restored %s from backup", RT_TABLES_PATH)
    else:
        # No saved content -- just remove sbr_ entries
        content = read_file(RT_TABLES_PATH) or ""
        lines = content.splitlines()
        new_lines = [
            line for line in lines
            if not (line.strip() and not line.strip().startswith("#")
                    and TABLE_NAME_PREFIX in line)
        ]
        # Remove our marker if present
        new_lines = [line for line in new_lines if line.strip() != MANAGED_COMMENT]
        write_file_atomic(RT_TABLES_PATH, "\n".join(new_lines) + "\n")
        logger.info("Removed sbr_ entries from %s", RT_TABLES_PATH)


def _restore_sbr_routes(saved: dict) -> None:
    """Re-add routes the backup recorded in sbr_ tables.

    Restores the previous running config: routes that existed in custom
    SBR tables at backup time come back, whether sbr-config created them
    or not. Subnet/link routes go first so default routes can resolve
    their gateway.
    """
    routes_by_table = saved.get("routes_by_table") or {}
    for table_name, route_dicts in routes_by_table.items():
        if not table_name.startswith(TABLE_NAME_PREFIX):
            continue
        ordered = sorted(
            route_dicts, key=lambda rd: rd.get("destination") == "default"
        )
        for rd in ordered:
            route = Route(
                destination=rd.get("destination", ""),
                gateway=rd.get("gateway"),
                device=rd.get("device", ""),
                source=rd.get("source"),
                table=table_name,
                metric=rd.get("metric"),
                scope=rd.get("scope"),
            )
            if not route.destination or not route.device:
                continue
            try:
                run_command(f"ip route replace {route.to_args()}", check=False)
                logger.info("Restored route: %s", route.to_args())
            except Exception as e:
                logger.warning("Failed to restore route '%s': %s", route.to_args(), e)


def _restore_sbr_rules(saved: dict) -> None:
    """Re-add IP rules the backup recorded pointing at sbr_ tables."""
    for rd in saved.get("rules") or []:
        table = rd.get("table")
        if not table or not str(table).startswith(TABLE_NAME_PREFIX):
            continue
        rule = Rule(
            priority=rd.get("priority", 0),
            selector_from=rd.get("selector_from"),
            selector_to=rd.get("selector_to"),
            table=table,
            iif=rd.get("iif"),
            fwmark=rd.get("fwmark"),
        )
        try:
            run_command(f"ip rule add {rule.to_args()}", check=False)
            logger.info("Restored rule: %s", rule.to_args())
        except Exception as e:
            logger.warning("Failed to restore rule '%s': %s", rule.to_args(), e)


def _restore_sysctl(saved: dict) -> None:
    """Restore sysctl values from backup.

    The sysctl persistence file is handled by the persistence snapshot
    restore, not here.
    """
    saved_values = saved.get("sysctl_values", {})
    for key, value in saved_values.items():
        if value and value != "unknown":
            try:
                run_command(f"sysctl -w {key}={value}", check=False)
                logger.info("Restored sysctl %s = %s", key, value)
            except Exception as e:
                logger.warning("Failed to restore sysctl %s: %s", key, e)


def _restore_persistence_files(saved: dict) -> None:
    """Restore persistence files to their backed-up contents.

    Files that existed at backup time get their saved content back; managed
    files created since are removed. Backups from before this snapshot was
    recorded fall back to removing all managed persistence files.
    """
    snapshot = saved.get("_persistence_files")
    if snapshot is None:
        _remove_persistence_files()
        return

    # Remove managed files that didn't exist at backup time. The main
    # interfaces file is never deleted -- it's user-owned; content restore
    # below handles any lines we appended to it.
    for path in _managed_file_paths():
        if snapshot.get(path) is None and path != INTERFACES_FILE:
            _remove_managed_file(path)

    # Restore recorded contents
    for path, content in snapshot.items():
        if content is None:
            continue
        current = read_file(path)
        if current == content:
            continue
        if path == INTERFACES_FILE and (current is None or MANAGED_COMMENT not in current):
            # Only rewrite the interfaces file if our own lines are in it;
            # otherwise the difference is someone else's edit.
            continue
        mode = 0o755 if path == NM_DISPATCHER_PATH else None
        write_file_atomic(path, content, mode=mode)
        logger.info("Restored %s from backup", path)


def _remove_persistence_files() -> None:
    """Remove all persistence files created by sbr-config.

    Fallback for backups saved before persistence snapshots existed.
    """
    # NetworkManager dispatcher script
    _remove_managed_file(NM_DISPATCHER_PATH)

    # Netplan config
    _remove_managed_file(os.path.join(NETPLAN_DIR, NETPLAN_CONFIG_FILE))

    # systemd-networkd drop-in files
    if os.path.isdir(SYSTEMD_NETWORK_DIR):
        for fname in os.listdir(SYSTEMD_NETWORK_DIR):
            if fname.startswith("50-sbr-"):
                _remove_managed_file(os.path.join(SYSTEMD_NETWORK_DIR, fname))

    # ifupdown files in interfaces.d
    if os.path.isdir(INTERFACES_D_DIR):
        for fname in os.listdir(INTERFACES_D_DIR):
            if fname.startswith("sbr-"):
                _remove_managed_file(os.path.join(INTERFACES_D_DIR, fname))

    # Sysctl persistence
    remove_sysctl_persistence()


def _remove_managed_file(path: str) -> None:
    """Remove a file only if it contains our managed comment."""
    if not os.path.exists(path):
        return
    content = read_file(path)
    if content and MANAGED_COMMENT in content:
        os.unlink(path)
        logger.info("Removed managed file: %s", path)
    else:
        logger.warning(
            "File %s exists but doesn't appear managed by sbr-config; skipping",
            path,
        )
