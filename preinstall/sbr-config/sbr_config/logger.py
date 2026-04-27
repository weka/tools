"""File logging setup for sbr-config."""

import logging
import os
from typing import Optional

from .constants import LOG_FILE_DEFAULT


def setup_logging(
    log_file: Optional[str] = None,
    verbosity: int = 0,
) -> None:
    """Configure logging for sbr-config.

    Args:
        log_file: Path to log file. None disables file logging.
        verbosity: 0=WARNING, 1=INFO, 2+=DEBUG.
    """
    root_logger = logging.getLogger("sbr_config")

    # Console level based on verbosity
    if verbosity >= 2:
        console_level = logging.DEBUG
    elif verbosity >= 1:
        console_level = logging.INFO
    else:
        console_level = logging.WARNING

    root_logger.setLevel(logging.DEBUG)  # Capture everything, handlers filter

    # File handler (always DEBUG level)
    if log_file is not None:
        path = log_file if log_file else LOG_FILE_DEFAULT
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fh = logging.FileHandler(path)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            root_logger.addHandler(fh)
        except PermissionError:
            # Non-fatal: can't write log file but tool should still work
            pass

    # Console handler (verbosity-controlled, only for debug output)
    if verbosity >= 1:
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root_logger.addHandler(ch)
