"""Shell command execution, atomic file writes, privilege checks, and lock management."""

import fcntl
import logging
import os
import platform
import subprocess
from typing import Optional

from .constants import LOCK_FILE
from .exceptions import ConfigurationError, LockError, PrivilegeError

logger = logging.getLogger(__name__)


def run_command(
    cmd: str,
    check: bool = True,
    timeout: int = 10,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a shell command, log it, return result.

    Args:
        cmd: Shell command string to execute.
        check: If True, raise ConfigurationError on non-zero exit.
        timeout: Command timeout in seconds.
        capture: If True, capture stdout/stderr.

    Returns:
        CompletedProcess instance.

    Raises:
        ConfigurationError: If check=True and command returns non-zero.
    """
    logger.debug("Running: %s", cmd)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            universal_newlines=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ConfigurationError(f"Command timed out after {timeout}s: {cmd}")

    if result.stdout:
        logger.debug("stdout: %s", result.stdout.rstrip())
    if result.stderr:
        logger.debug("stderr: %s", result.stderr.rstrip())

    if check and result.returncode != 0:
        raise ConfigurationError(
            f"Command failed (exit {result.returncode}): {cmd}\n"
            f"stderr: {result.stderr.rstrip()}"
        )
    return result


def write_file_atomic(path: str, content: str, mode: Optional[int] = None) -> None:
    """Write content to file atomically via temp file + rename.

    Args:
        path: Destination file path.
        content: File content to write.
        mode: File permission mode. If None, preserves existing or uses 0o644.
    """
    tmp_path = path + ".sbr-config.tmp"
    try:
        # Determine permissions to use
        if mode is not None:
            file_mode = mode
        elif os.path.exists(path):
            file_mode = os.stat(path).st_mode & 0o7777
        else:
            file_mode = 0o644

        with open(tmp_path, "w") as f:
            f.write(content)
        os.chmod(tmp_path, file_mode)
        os.rename(tmp_path, path)
        logger.debug("Wrote %s (%d bytes)", path, len(content))
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def read_file(path: str) -> Optional[str]:
    """Read a file's contents, returning None if it doesn't exist."""
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except PermissionError:
        logger.warning("Permission denied reading %s", path)
        return None


def check_root() -> None:
    """Verify running as root."""
    if os.geteuid() != 0:
        raise PrivilegeError("sbr-config must be run as root (try: sudo sbr-config ...)")


def is_linux() -> bool:
    """Check if running on Linux."""
    return platform.system() == "Linux"


def command_exists(name: str) -> bool:
    """Check if a command is available in PATH."""
    result = subprocess.run(
        ["which", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return result.returncode == 0


def ip_json_supported() -> bool:
    """Check if `ip -j` (JSON output) is supported."""
    try:
        result = subprocess.run(
            "ip -j link show lo",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip().startswith("[")
    except Exception:
        return False


class FileLock:
    """Simple file-based lock using flock.

    Usage:
        with FileLock():
            # critical section
    """

    def __init__(self, path: str = LOCK_FILE):
        self.path = path
        self._fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._fd = open(self.path, "w")
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fd.close()
            raise LockError(
                "Another sbr-config instance is running. "
                f"If this is wrong, remove {self.path}"
            )
        self._fd.write(str(os.getpid()))
        self._fd.flush()
        return self

    def __exit__(self, *args):
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
