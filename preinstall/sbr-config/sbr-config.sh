#!/usr/bin/env bash
# sbr-config: Linux Source-Based Routing Configuration Tool
# This wrapper validates the environment and delegates to the Python core.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=6

error() {
    echo "ERROR: $*" >&2
    exit 1
}

warn() {
    echo "WARNING: $*" >&2
}

# ---------------------------------------------------------------------------
# Determine if this invocation needs root or is info-only
# --help, -h, --version, and --check-prereqs/-p can run without root/Linux
# ---------------------------------------------------------------------------
NEEDS_ROOT=true
for arg in "$@"; do
    case "$arg" in
        --help|-h|--version|--check-prereqs|-p)
            NEEDS_ROOT=false
            break
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

# Check OS (allow --help/--version/--check-prereqs on any OS)
if [[ "$(uname -s)" != "Linux" ]]; then
    if $NEEDS_ROOT; then
        error "sbr-config only runs on Linux (detected: $(uname -s))"
    fi
fi

# Find Python 3.6+
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        major=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null) || continue
        minor=$("$candidate" -c "import sys; print(sys.version_info.minor)" 2>/dev/null) || continue
        if [[ "$major" -ge "$MIN_PYTHON_MAJOR" ]] && [[ "$minor" -ge "$MIN_PYTHON_MINOR" ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    error "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required but not found. Install python3 and try again."
fi

# Check for root (skip for info-only commands)
if $NEEDS_ROOT && [[ $EUID -ne 0 ]]; then
    error "sbr-config must be run as root (try: sudo $0 $*)"
fi

# Check iproute2 (skip for info-only commands, warn but don't block)
if $NEEDS_ROOT && ! command -v ip &>/dev/null; then
    error "'ip' command not found. Install the iproute2 package."
fi

# ---------------------------------------------------------------------------
# Handle --check-prereqs directly in bash (comprehensive check)
# ---------------------------------------------------------------------------
for arg in "$@"; do
    if [[ "$arg" == "--check-prereqs" ]] || [[ "$arg" == "-p" ]]; then
        echo ""
        echo "sbr-config: Prerequisite Check"
        echo "=============================="
        echo ""
        PASS_COUNT=0
        FAIL_COUNT=0
        WARN_COUNT=0

        # Helper functions
        check_pass()  { echo "  [PASS] $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
        check_fail()  { echo "  [FAIL] $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
        check_warn()  { echo "  [WARN] $1"; WARN_COUNT=$((WARN_COUNT + 1)); }
        check_info()  { echo "  [INFO] $1"; }

        # --- Required ---
        echo "Required:"
        echo "  -------"

        # OS
        if [[ "$(uname -s)" == "Linux" ]]; then
            DISTRO=""
            if [[ -f /etc/os-release ]]; then
                DISTRO=$(. /etc/os-release && echo "${PRETTY_NAME:-$ID}")
            fi
            check_pass "Linux OS: $(uname -r) ${DISTRO:+($DISTRO)}"
        else
            check_fail "Linux OS required (detected: $(uname -s))"
        fi

        # Python
        if [[ -n "$PYTHON" ]]; then
            PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
            check_pass "Python: $PY_VERSION ($PYTHON)"
        else
            check_fail "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ not found"
        fi

        # iproute2
        if command -v ip &>/dev/null; then
            IP_VERSION=$(ip -V 2>&1 | head -1)
            check_pass "iproute2: $IP_VERSION"

            # Check ip -j support
            if ip -j link show lo &>/dev/null 2>&1; then
                check_pass "iproute2 JSON mode (-j): supported"
            else
                check_warn "iproute2 JSON mode (-j): not supported (will use text parsing fallback)"
            fi
        else
            check_fail "iproute2 (ip command) not found -- install iproute2 package"
        fi

        # sysctl
        if command -v sysctl &>/dev/null; then
            check_pass "sysctl: $(which sysctl)"
        else
            check_fail "sysctl not found -- install procps package"
        fi

        # Root privileges
        if [[ $EUID -eq 0 ]]; then
            check_pass "Root privileges: running as root (UID 0)"
        else
            check_warn "Root privileges: not running as root (required for --configure and --rollback)"
        fi

        # /etc/iproute2/rt_tables
        if [[ -f /etc/iproute2/rt_tables ]]; then
            check_pass "/etc/iproute2/rt_tables: exists"
            if [[ -w /etc/iproute2/rt_tables ]] || [[ $EUID -eq 0 ]]; then
                check_pass "/etc/iproute2/rt_tables: writable"
            else
                check_warn "/etc/iproute2/rt_tables: not writable (need root)"
            fi
        else
            check_fail "/etc/iproute2/rt_tables: not found"
        fi

        # Multiple interfaces
        echo ""
        echo "Network Interfaces:"
        echo "  ------------------"
        if command -v ip &>/dev/null; then
            IFACE_COUNT=0
            while IFS= read -r line; do
                IFACE_NAME=$(echo "$line" | awk '{print $2}' | tr -d ':')
                # Skip loopback
                if [[ "$IFACE_NAME" == "lo" ]]; then continue; fi
                IFACE_COUNT=$((IFACE_COUNT + 1))
                # Get IP if possible
                IFACE_IP=$(ip -4 addr show "$IFACE_NAME" 2>/dev/null | grep -oP 'inet \K[\d.]+/\d+' | head -1)
                if [[ -n "$IFACE_IP" ]]; then
                    check_info "$IFACE_NAME: $IFACE_IP"
                else
                    check_info "$IFACE_NAME: no IPv4 address"
                fi
            done < <(ip -o link show up 2>/dev/null | grep -v 'lo:')
            echo ""
            if [[ $IFACE_COUNT -ge 2 ]]; then
                check_pass "Multiple interfaces detected ($IFACE_COUNT) -- SBR is applicable"
            elif [[ $IFACE_COUNT -eq 1 ]]; then
                check_warn "Only 1 non-loopback interface -- SBR requires 2+ interfaces"
            else
                check_warn "No active non-loopback interfaces found"
            fi
        fi

        # --- Optional (for persistence) ---
        echo ""
        echo "Persistence Backends (optional, for --persist):"
        echo "  ------------------------------------------------"

        # NetworkManager
        if command -v nmcli &>/dev/null; then
            NM_STATUS=$(systemctl is-active NetworkManager.service 2>/dev/null || echo "inactive")
            if [[ "$NM_STATUS" == "active" ]]; then
                check_pass "NetworkManager: active"
            else
                check_info "NetworkManager: installed but $NM_STATUS"
            fi
        else
            check_info "NetworkManager: not installed"
        fi

        # systemd-networkd
        NETWORKD_STATUS=$(systemctl is-active systemd-networkd.service 2>/dev/null || echo "inactive")
        if [[ "$NETWORKD_STATUS" == "active" ]]; then
            check_pass "systemd-networkd: active"
        else
            check_info "systemd-networkd: $NETWORKD_STATUS"
        fi

        # netplan
        if command -v netplan &>/dev/null; then
            check_pass "netplan: $(which netplan)"
        else
            check_info "netplan: not installed"
        fi

        # ifupdown
        if command -v ifup &>/dev/null || command -v ifdown &>/dev/null; then
            if [[ -f /etc/network/interfaces ]]; then
                check_pass "ifupdown: available (/etc/network/interfaces exists)"
            else
                check_info "ifupdown: commands found but /etc/network/interfaces missing"
            fi
        else
            check_info "ifupdown: not installed"
        fi

        # --- Summary ---
        echo ""
        echo "  =============================="
        TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))
        echo "  Summary: $PASS_COUNT passed, $FAIL_COUNT failed, $WARN_COUNT warnings (of $TOTAL checks)"

        if [[ $FAIL_COUNT -gt 0 ]]; then
            echo ""
            echo "  Some required prerequisites are missing. Install them before using sbr-config."
            exit 1
        else
            echo ""
            echo "  All required prerequisites are met. Ready to use sbr-config."
            exit 0
        fi
    fi
done

# ---------------------------------------------------------------------------
# Delegate to Python package
# ---------------------------------------------------------------------------
if "$PYTHON" -c "import sbr_config" 2>/dev/null; then
    exec "$PYTHON" -m sbr_config "$@"
elif [[ -d "${SCRIPT_DIR}/sbr_config" ]]; then
    export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"
    exec "$PYTHON" -m sbr_config "$@"
else
    error "sbr_config Python package not found. Ensure sbr_config/ is in the same directory as this script or install via pip."
fi
