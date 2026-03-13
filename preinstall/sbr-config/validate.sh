#!/usr/bin/env bash
# ============================================================================
# sbr-config Go Rewrite Validation Script
#
# Run as root on a Linux system with 2+ NICs.
# Both the Go binary and Python source must be present.
#
# Usage:
#   sudo bash validate.sh /tmp/sbr-config-go /path/to/sbr-config.sh
#
# Output:  /tmp/sbr-validate/ directory with all captures + report.txt
# ============================================================================

set -uo pipefail

GO_BIN="${1:?Usage: $0 <go-binary> <python-wrapper>}"
PY_BIN="${2:?Usage: $0 <go-binary> <python-wrapper>}"
OUT="/tmp/sbr-validate"

RED='\033[0;31m'
GRN='\033[0;32m'
YEL='\033[1;33m'
NC='\033[0m'

die()  { echo -e "${RED}FATAL: $*${NC}" >&2; exit 1; }
pass() { echo -e "${GRN}  PASS: $*${NC}"; echo "PASS: $*" >> "$OUT/report.txt"; }
fail() { echo -e "${RED}  FAIL: $*${NC}"; echo "FAIL: $*" >> "$OUT/report.txt"; FAILURES=$((FAILURES+1)); }
info() { echo -e "${YEL}>>> $*${NC}"; echo "--- $* ---" >> "$OUT/report.txt"; }
FAILURES=0

# ── Pre-flight ──────────────────────────────────────────────────────────────

[[ $(id -u) -eq 0 ]] || die "Must run as root"
[[ -x "$GO_BIN" ]]   || die "Go binary not found or not executable: $GO_BIN"
[[ -f "$PY_BIN" ]]    || die "Python wrapper not found: $PY_BIN"

rm -rf "$OUT"
mkdir -p "$OUT"
echo "=== sbr-config validation $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" > "$OUT/report.txt"
echo "Go binary:  $GO_BIN" >> "$OUT/report.txt"
echo "Py wrapper: $PY_BIN" >> "$OUT/report.txt"
echo "" >> "$OUT/report.txt"

# Helper: snapshot routing state into a given prefix
snapshot() {
    local pfx="$1"
    ip rule show                          > "$OUT/${pfx}-rules.txt"     2>&1
    ip route show table all               > "$OUT/${pfx}-routes.txt"    2>&1
    cat /etc/iproute2/rt_tables           > "$OUT/${pfx}-rt_tables.txt" 2>&1
    sysctl -a 2>/dev/null | grep -E 'rp_filter|arp_filter|arp_announce' \
                                          > "$OUT/${pfx}-sysctl.txt"    2>&1
    # Persistence files (capture whichever exist)
    cp /etc/sysctl.d/90-sbr-config.conf              "$OUT/${pfx}-persist-sysctl.txt"  2>/dev/null || true
    cp /etc/NetworkManager/dispatcher.d/50-sbr-config "$OUT/${pfx}-persist-nm.txt"      2>/dev/null || true
    # systemd-networkd: may be multiple files
    cat /etc/systemd/network/50-sbr-*.network         > "$OUT/${pfx}-persist-networkd.txt" 2>/dev/null || true
    cp /etc/netplan/90-sbr-config.yaml                "$OUT/${pfx}-persist-netplan.txt" 2>/dev/null || true
    # ifupdown drop-ins
    cat /etc/network/interfaces.d/sbr-*               > "$OUT/${pfx}-persist-ifupdown.txt" 2>/dev/null || true
    # Backup dir listing
    ls -la /var/lib/sbr-config/backups/               > "$OUT/${pfx}-backups-ls.txt" 2>/dev/null || true
}

# ============================================================================
info "TEST 1: --version"
# ============================================================================

"$GO_BIN" --version > "$OUT/go-version.txt" 2>&1
GO_RC=$?
echo "EXIT: $GO_RC" >> "$OUT/go-version.txt"

bash "$PY_BIN" --version > "$OUT/py-version.txt" 2>&1
PY_RC=$?
echo "EXIT: $PY_RC" >> "$OUT/py-version.txt"

[[ $GO_RC -eq 0 ]] && pass "--version exits 0" || fail "--version exits $GO_RC (expected 0)"
grep -q "sbr-config" "$OUT/go-version.txt" && pass "--version prints version string" || fail "--version output missing 'sbr-config'"

# ============================================================================
info "TEST 2: --help"
# ============================================================================

"$GO_BIN" --help > "$OUT/go-help.txt" 2>&1
GO_RC=$?
echo "EXIT: $GO_RC" >> "$OUT/go-help.txt"

bash "$PY_BIN" --help > "$OUT/py-help.txt" 2>&1 || true

[[ $GO_RC -eq 0 ]] && pass "--help exits 0" || fail "--help exits $GO_RC (expected 0)"
# Check key flags present
for flag in "--validate" "--configure" "--rollback" "--check-prereqs" "--force" "--no-persist" "--dry-run" "--confirm-timeout" "--exclude" "--include" "--backup-file"; do
    grep -q -- "$flag" "$OUT/go-help.txt" && pass "--help contains $flag" || fail "--help missing $flag"
done

# ============================================================================
info "TEST 3: --check-prereqs (-p)"
# ============================================================================

"$GO_BIN" -p > "$OUT/go-prereqs.txt" 2>&1
GO_RC=$?
echo "EXIT: $GO_RC" >> "$OUT/go-prereqs.txt"

bash "$PY_BIN" -p > "$OUT/py-prereqs.txt" 2>&1
PY_RC=$?
echo "EXIT: $PY_RC" >> "$OUT/py-prereqs.txt"

[[ $GO_RC -eq 0 ]] && pass "-p exits 0" || fail "-p exits $GO_RC (expected 0)"
[[ $GO_RC -eq $PY_RC ]] && pass "-p exit codes match (Go=$GO_RC, Py=$PY_RC)" || fail "-p exit codes differ (Go=$GO_RC, Py=$PY_RC)"

# ============================================================================
info "TEST 4: --validate (-V)  [read-only, safe]"
# ============================================================================

"$GO_BIN" -V > "$OUT/go-validate.txt" 2>&1
GO_RC=$?
echo "EXIT: $GO_RC" >> "$OUT/go-validate.txt"

bash "$PY_BIN" -V > "$OUT/py-validate.txt" 2>&1
PY_RC=$?
echo "EXIT: $PY_RC" >> "$OUT/py-validate.txt"

[[ $GO_RC -eq $PY_RC ]] && pass "-V exit codes match (Go=$GO_RC, Py=$PY_RC)" || fail "-V exit codes differ (Go=$GO_RC, Py=$PY_RC)"

# ============================================================================
info "TEST 5: --configure --dry-run (-c -n)  [read-only, safe]"
# ============================================================================

"$GO_BIN" -c -n > "$OUT/go-dryrun.txt" 2>&1
GO_RC=$?
echo "EXIT: $GO_RC" >> "$OUT/go-dryrun.txt"

bash "$PY_BIN" -c -n > "$OUT/py-dryrun.txt" 2>&1
PY_RC=$?
echo "EXIT: $PY_RC" >> "$OUT/py-dryrun.txt"

[[ $GO_RC -eq $PY_RC ]] && pass "-c -n exit codes match (Go=$GO_RC, Py=$PY_RC)" || fail "-c -n exit codes differ (Go=$GO_RC, Py=$PY_RC)"

# ============================================================================
info "TEST 6a: Configure with PYTHON (reference state) (-c -f -t 0)"
# ============================================================================

# Clean any stale SBR state from prior runs
if grep -q 'sbr_' /etc/iproute2/rt_tables 2>/dev/null; then
    echo "  Cleaning stale SBR state before reference test..."
    "$GO_BIN" -r -f > /dev/null 2>&1 || bash "$PY_BIN" -r -f > /dev/null 2>&1 || true
fi

# Clean backups first to avoid confusion
rm -rf /var/lib/sbr-config/backups/*

bash "$PY_BIN" -c -f -t 0 > "$OUT/py-configure.txt" 2>&1
PY_RC=$?
echo "EXIT: $PY_RC" >> "$OUT/py-configure.txt"

[[ $PY_RC -eq 0 ]] && pass "Python configure exits 0" || fail "Python configure exits $PY_RC"

# ============================================================================
info "TEST 6b: Snapshot Python reference state"
# ============================================================================

snapshot "ref"
# Also save the Python backup JSON
cp /var/lib/sbr-config/backups/state_*.json "$OUT/py-backup.json" 2>/dev/null || true

echo "  Captured ref-rules.txt, ref-routes.txt, ref-rt_tables.txt, ref-sysctl.txt"
echo "  Captured ref-persist-*.txt files"

# ============================================================================
info "TEST 6c: Rollback with PYTHON (clean slate)"
# ============================================================================

bash "$PY_BIN" -r -f > "$OUT/py-rollback.txt" 2>&1
PY_RC=$?
echo "EXIT: $PY_RC" >> "$OUT/py-rollback.txt"

[[ $PY_RC -eq 0 ]] && pass "Python rollback exits 0" || fail "Python rollback exits $PY_RC"

snapshot "post-py-rollback"

# ============================================================================
info "TEST 6d: Configure with GO (-c -f -t 0)"
# ============================================================================

# Clean backups first
rm -rf /var/lib/sbr-config/backups/*

"$GO_BIN" -c -f -t 0 > "$OUT/go-configure.txt" 2>&1
GO_RC=$?
echo "EXIT: $GO_RC" >> "$OUT/go-configure.txt"

[[ $GO_RC -eq 0 ]] && pass "Go configure exits 0" || fail "Go configure exits $GO_RC"

# ============================================================================
info "TEST 6e: Snapshot Go state"
# ============================================================================

snapshot "go"

echo "  Captured go-rules.txt, go-routes.txt, go-rt_tables.txt, go-sysctl.txt"
echo "  Captured go-persist-*.txt files"

# ============================================================================
info "TEST 6f: Compare Python vs Go state (the critical diff)"
# ============================================================================

# --- IP rules ---
# Sort both to ignore ordering differences, strip priority numbers which may differ
# due to timing, but compare the from/table structure
diff <(sed 's/^[0-9]*:\t//' "$OUT/ref-rules.txt" | sort) \
     <(sed 's/^[0-9]*:\t//' "$OUT/go-rules.txt"  | sort) \
     > "$OUT/diff-rules.txt" 2>&1
[[ $? -eq 0 ]] && pass "IP rules match" || fail "IP rules differ (see diff-rules.txt)"

# --- Routing tables (filter to only SBR tables) ---
diff <(grep 'table sbr_' "$OUT/ref-routes.txt" | sort) \
     <(grep 'table sbr_' "$OUT/go-routes.txt"  | sort) \
     > "$OUT/diff-routes.txt" 2>&1
[[ $? -eq 0 ]] && pass "SBR routing tables match" || fail "SBR routing tables differ (see diff-routes.txt)"

# --- rt_tables file (filter to sbr_ entries) ---
diff <(grep 'sbr_' "$OUT/ref-rt_tables.txt" | sort) \
     <(grep 'sbr_' "$OUT/go-rt_tables.txt"  | sort) \
     > "$OUT/diff-rt_tables.txt" 2>&1
[[ $? -eq 0 ]] && pass "rt_tables entries match" || fail "rt_tables entries differ (see diff-rt_tables.txt)"

# --- sysctl ---
diff "$OUT/ref-sysctl.txt" "$OUT/go-sysctl.txt" \
     > "$OUT/diff-sysctl.txt" 2>&1
[[ $? -eq 0 ]] && pass "sysctl settings match" || fail "sysctl settings differ (see diff-sysctl.txt)"

# --- Persistence files (compare whichever exist) ---
for suffix in sysctl nm networkd netplan ifupdown; do
    REF="$OUT/ref-persist-${suffix}.txt"
    GOF="$OUT/go-persist-${suffix}.txt"
    if [[ -s "$REF" ]] || [[ -s "$GOF" ]]; then
        if [[ -s "$REF" ]] && [[ -s "$GOF" ]]; then
            diff "$REF" "$GOF" > "$OUT/diff-persist-${suffix}.txt" 2>&1
            [[ $? -eq 0 ]] && pass "Persistence ($suffix) matches" || fail "Persistence ($suffix) differs (see diff-persist-${suffix}.txt)"
        elif [[ -s "$REF" ]]; then
            fail "Persistence ($suffix) exists for Python but not Go"
        else
            fail "Persistence ($suffix) exists for Go but not Python"
        fi
    fi
done

# ============================================================================
info "TEST 7: Go rollback of Go backup"
# ============================================================================

"$GO_BIN" -r -f > "$OUT/go-rollback.txt" 2>&1
GO_RC=$?
echo "EXIT: $GO_RC" >> "$OUT/go-rollback.txt"

[[ $GO_RC -eq 0 ]] && pass "Go rollback exits 0" || fail "Go rollback exits $GO_RC"

snapshot "post-go-rollback"

# Verify SBR rules are gone
SBR_RULES=$(grep -c 'sbr_' "$OUT/post-go-rollback-rules.txt" 2>/dev/null) || SBR_RULES=0
[[ "$SBR_RULES" -eq 0 ]] && pass "Go rollback removed all SBR rules" || fail "Go rollback left $SBR_RULES SBR rules"

SBR_TABLES=$(grep -c 'sbr_' "$OUT/post-go-rollback-rt_tables.txt" 2>/dev/null) || SBR_TABLES=0
[[ "$SBR_TABLES" -eq 0 ]] && pass "Go rollback removed all SBR table entries" || fail "Go rollback left $SBR_TABLES SBR table entries"

# ============================================================================
info "TEST 8: Backward compat — Go rollback of Python backup"
# ============================================================================

# Ensure clean state: unconditional rollback + persistence cleanup
"$GO_BIN" -r -f > /dev/null 2>&1 || true
rm -f /etc/sysctl.d/90-sbr-config.conf /etc/netplan/90-sbr-config.yaml
netplan apply 2>/dev/null || true

# Re-apply with Python to create a fresh backup
rm -rf /var/lib/sbr-config/backups/*
bash "$PY_BIN" -c -f -t 0 > "$OUT/py-reapply-cross.txt" 2>&1
PY_RC=$?
[[ $PY_RC -eq 0 ]] || { fail "Python re-apply for cross-compat test failed ($PY_RC)"; }

LATEST_BACKUP=$(ls -t /var/lib/sbr-config/backups/state_*.json 2>/dev/null | head -1)
if [[ -z "$LATEST_BACKUP" ]]; then
    fail "No Python backup found for cross-compat test"
else
    echo "  Using Python backup: $LATEST_BACKUP"
    cp "$LATEST_BACKUP" "$OUT/py-backup-for-cross.json"

    "$GO_BIN" -r -f -b "$LATEST_BACKUP" > "$OUT/go-rollback-py-backup.txt" 2>&1
    GO_RC=$?
    echo "EXIT: $GO_RC" >> "$OUT/go-rollback-py-backup.txt"

    [[ $GO_RC -eq 0 ]] && pass "Go rollback of Python backup exits 0" || fail "Go rollback of Python backup exits $GO_RC"

    snapshot "post-cross-rollback"

    SBR_RULES=$(grep -c 'sbr_' "$OUT/post-cross-rollback-rules.txt" 2>/dev/null) || SBR_RULES=0
    [[ "$SBR_RULES" -eq 0 ]] && pass "Cross rollback removed all SBR rules" || fail "Cross rollback left $SBR_RULES SBR rules"
fi

# ============================================================================
info "TEST 9: Dead man's switch (auto-rollback after timeout)"
# ============================================================================

echo ""
echo -e "${YEL}  This test applies changes then waits for a 10-second timer to expire.${NC}"
echo -e "${YEL}  DO NOT press any keys. The auto-rollback should trigger.${NC}"
echo ""

# Make sure SBR is not currently configured (clean state)
# Apply with Go, then let the dead man's switch fire
# We pipe /dev/null to stdin for the pre-apply prompt (force handles that)
# and use 'yes' piped to handle the pre-apply "Apply N change(s)?" if needed,
# but then no input for the timed confirm.

# First, make sure there's something to configure
"$GO_BIN" -V > /dev/null 2>&1
NEED_CONFIG=$?

if [[ $NEED_CONFIG -eq 0 ]]; then
    echo "  System already configured; rolling back first to create test conditions."
    "$GO_BIN" -r -f > /dev/null 2>&1 || bash "$PY_BIN" -r -f > /dev/null 2>&1 || true
fi

# Apply with a short timer. 'yes' provides 'y' for the pre-apply prompt,
# then stdin hits EOF for the timed confirm → timeout fires.
rm -rf /var/lib/sbr-config/backups/*
echo y | timeout 30 "$GO_BIN" -c -t 10 > "$OUT/go-deadman.txt" 2>&1
DM_RC=$?
echo "EXIT: $DM_RC" >> "$OUT/go-deadman.txt"

# The dead man's switch should auto-rollback and exit 1
if grep -qi "rolling back" "$OUT/go-deadman.txt"; then
    pass "Dead man's switch triggered auto-rollback"
else
    fail "Dead man's switch did NOT trigger (check go-deadman.txt)"
fi

snapshot "post-deadman"

# ============================================================================
info "FINAL: Clean up — leave system in original state"
# ============================================================================

# If SBR rules still exist, roll back
if grep -q 'sbr_' /etc/iproute2/rt_tables 2>/dev/null; then
    echo "  Cleaning up residual SBR state..."
    "$GO_BIN" -r -f > /dev/null 2>&1 || bash "$PY_BIN" -r -f > /dev/null 2>&1 || true
fi

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "============================================"
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GRN}ALL TESTS PASSED${NC}"
else
    echo -e "${RED}$FAILURES TEST(S) FAILED${NC}"
fi
echo "============================================"
echo ""
echo "Full report:  $OUT/report.txt"
echo "All captures: $OUT/"
echo ""
echo "To collect everything:"
echo "  tar czf /tmp/sbr-validation.tar.gz -C /tmp sbr-validate/"
echo ""

# Append summary to report
echo "" >> "$OUT/report.txt"
echo "============================================" >> "$OUT/report.txt"
if [[ $FAILURES -eq 0 ]]; then
    echo "ALL TESTS PASSED" >> "$OUT/report.txt"
else
    echo "$FAILURES TEST(S) FAILED" >> "$OUT/report.txt"
fi
echo "============================================" >> "$OUT/report.txt"

exit $FAILURES
