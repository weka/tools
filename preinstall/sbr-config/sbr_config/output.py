"""Colored terminal output, formatting, tables, and interactive prompts."""

import select
import sys
import time
from typing import List, Optional

from .models import PlannedChange, ValidationResult


class Colors:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


class Output:
    """Handles all user-facing terminal output."""

    def __init__(self, color: bool = True, quiet: bool = False):
        self._color = color
        self._quiet = quiet

    def _c(self, code: str, text: str) -> str:
        """Apply color code if colors are enabled."""
        if not self._color:
            return text
        return f"{code}{text}{Colors.RESET}"

    def header(self, text: str) -> None:
        """Print a section header."""
        if self._quiet:
            return
        print()
        print(self._c(Colors.BOLD + Colors.BLUE, text))
        print(self._c(Colors.BOLD + Colors.BLUE, "=" * len(text)))

    def subheader(self, text: str) -> None:
        """Print a sub-section header."""
        if self._quiet:
            return
        print()
        print(self._c(Colors.BOLD + Colors.CYAN, text))
        print(self._c(Colors.DIM, "-" * len(text)))

    def success(self, text: str) -> None:
        """Print a success message."""
        if self._quiet:
            return
        prefix = self._c(Colors.GREEN, "[PASS]")
        print(f"  {prefix} {text}")

    def fail(self, text: str) -> None:
        """Print a failure message."""
        prefix = self._c(Colors.RED, "[FAIL]")
        print(f"  {prefix} {text}")

    def warning(self, text: str) -> None:
        """Print a warning message."""
        prefix = self._c(Colors.YELLOW, "[WARN]")
        print(f"  {prefix} {text}")

    def error(self, text: str) -> None:
        """Print an error message to stderr."""
        prefix = self._c(Colors.RED + Colors.BOLD, "ERROR:")
        print(f"{prefix} {text}", file=sys.stderr)

    def info(self, text: str) -> None:
        """Print an informational message."""
        if self._quiet:
            return
        prefix = self._c(Colors.CYAN, "[INFO]")
        print(f"  {prefix} {text}")

    def dim(self, text: str) -> None:
        """Print dimmed/secondary text."""
        if self._quiet:
            return
        print(f"  {self._c(Colors.DIM, text)}")

    def nl(self) -> None:
        """Print a blank line."""
        if not self._quiet:
            print()

    def banner(self) -> None:
        """Print the tool banner."""
        if self._quiet:
            return
        title = "sbr-config: Source-Based Routing Configurator"
        print()
        print(self._c(Colors.BOLD + Colors.WHITE, title))
        print(self._c(Colors.DIM, "=" * len(title)))

    def interface_table(self, interfaces: list) -> None:
        """Print a formatted table of detected interfaces."""
        if self._quiet:
            return
        # Header
        fmt = "  {:<12} {:<20} {:<16} {}"
        print(fmt.format("INTERFACE", "IP/PREFIX", "GATEWAY", "STATUS"))
        print(fmt.format("-" * 11, "-" * 19, "-" * 15, "-" * 20))
        for iface in interfaces:
            if iface.is_loopback:
                continue
            gw = iface.gateway or "(none)"
            status_parts = []
            if iface.is_default_route_interface:
                status_parts.append(self._c(Colors.GREEN, "DEFAULT ROUTE"))
            if not iface.is_up:
                status_parts.append(self._c(Colors.YELLOW, "DOWN"))
            status = " | ".join(status_parts) if status_parts else self._c(Colors.DIM, "secondary")
            print(fmt.format(iface.name, iface.cidr, gw, status))

    def validation_report(self, results: List[ValidationResult]) -> None:
        """Print a formatted validation report."""
        if not results:
            self.info("No validation checks to report.")
            return

        current_iface = None
        for r in results:
            if r.interface_name != current_iface:
                current_iface = r.interface_name
                self.subheader(f"Interface: {current_iface}")

            if r.is_correct:
                self.success(f"{r.check_name}: {r.current_value}")
            else:
                self.fail(f"{r.check_name}")
                self.dim(f"  Current:  {r.current_value}")
                self.dim(f"  Expected: {r.expected_value}")
                if r.fix_description:
                    self.dim(f"  Fix:      {r.fix_description}")

    def changes_report(self, changes: List[PlannedChange]) -> None:
        """Print proposed changes with explanations."""
        if not changes:
            self.info("No changes needed -- system is correctly configured.")
            return

        for i, change in enumerate(changes, 1):
            tag = self._c(Colors.BOLD + Colors.YELLOW, f"  {i}.")
            desc = self._c(Colors.BOLD, change.description)
            print(f"{tag} {desc}")

            # Command
            cmd_prefix = self._c(Colors.DIM, "     CMD:")
            cmd = self._c(Colors.CYAN, change.command)
            print(f"{cmd_prefix} {cmd}")

            # Reason (word-wrap at ~70 chars with indent)
            reason_prefix = self._c(Colors.DIM, "     WHY:")
            lines = _wrap_text(change.reason, width=65)
            print(f"{reason_prefix} {lines[0]}")
            for line in lines[1:]:
                print(f"          {line}")
            print()

    def prompt_yn(self, question: str, default: bool = False) -> bool:
        """Prompt user for yes/no answer.

        Args:
            question: The question to ask.
            default: Default answer if user just hits Enter.

        Returns:
            True for yes, False for no.
        """
        suffix = "[Y/n]" if default else "[y/N]"
        try:
            answer = input(f"\n{question} {suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if not answer:
            return default
        return answer in ("y", "yes")

    def prompt_timed_confirm(self, timeout: int) -> bool:
        """Post-apply dead man's switch confirmation.

        Displays a prominent warning and waits for the user to type 'yes'
        within ``timeout`` seconds.  If no confirmation is received the
        caller should automatically roll back.

        Args:
            timeout: Seconds to wait.  Must be > 0.

        Returns:
            True if the user confirmed, False if timeout expired or input
            was anything other than 'yes'.
        """
        box_w = 66
        border = self._c(Colors.RED + Colors.BOLD, "#" * box_w)
        pad = self._c(Colors.RED + Colors.BOLD, "#") + " " * (box_w - 2) + self._c(Colors.RED + Colors.BOLD, "#")

        print()
        print(border)
        print(pad)
        self._box_line("CONNECTIVITY CHECK", box_w, Colors.RED + Colors.BOLD)
        print(pad)
        self._box_line("Changes have been applied. Please verify that you", box_w, Colors.YELLOW)
        self._box_line("still have connectivity to this system.", box_w, Colors.YELLOW)
        print(pad)
        self._box_line("Type 'yes' within %d seconds to KEEP the changes." % timeout, box_w, Colors.WHITE + Colors.BOLD)
        self._box_line("If no response is received, all changes will be", box_w, Colors.WHITE)
        self._box_line("AUTOMATICALLY ROLLED BACK for safety.", box_w, Colors.WHITE)
        print(pad)
        print(border)
        print()

        deadline = time.time() + timeout
        confirmed = False

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            # Show countdown
            sys.stdout.write(
                "\r" + self._c(Colors.YELLOW + Colors.BOLD,
                               "  [%2ds] " % int(remaining + 0.5))
                + "Type 'yes' to confirm: "
            )
            sys.stdout.flush()

            try:
                ready, _, _ = select.select([sys.stdin], [], [], 1.0)
            except (OSError, ValueError):
                # stdin closed or not selectable
                break

            if ready:
                try:
                    answer = sys.stdin.readline().strip().lower()
                except (EOFError, IOError):
                    break
                if answer == "yes":
                    confirmed = True
                    break
                elif answer:
                    # Wrong answer -- remind them
                    sys.stdout.write(
                        "  " + self._c(Colors.RED, "Please type exactly 'yes' to confirm.") + "\n"
                    )

        # Clear the countdown line
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

        return confirmed

    def _box_line(self, text, width, color_code):
        """Print a centered line inside a bordered box."""
        inner = width - 4  # account for "# " and " #"
        padded = text.center(inner)
        left = self._c(Colors.RED + Colors.BOLD, "# ")
        right = self._c(Colors.RED + Colors.BOLD, " #")
        middle = self._c(color_code, padded)
        print(left + middle + right)

    def summary(self, passed: int, failed: int) -> None:
        """Print a validation summary line."""
        total = passed + failed
        if failed == 0:
            msg = self._c(Colors.GREEN + Colors.BOLD, f"All {total} checks passed")
        else:
            msg = (
                self._c(Colors.GREEN, f"{passed} passed") +
                ", " +
                self._c(Colors.RED + Colors.BOLD, f"{failed} failed") +
                f" (out of {total})"
            )
        print()
        print(f"  Summary: {msg}")


def _wrap_text(text: str, width: int = 70) -> List[str]:
    """Simple word-wrap without importing textwrap."""
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if current_line and len(current_line) + 1 + len(word) > width:
            lines.append(current_line)
            current_line = word
        else:
            current_line = f"{current_line} {word}" if current_line else word
    if current_line:
        lines.append(current_line)
    return lines or [""]
