#!/usr/bin/env bash
# Runs the upgrade checker's tests against a git snapshot, never the live tree:
# importing the checker truncates its log and may pip-install, so every test
# gets a `git archive` copy in a fresh scratch dir, with stubs for ssh/sudo/id.
# Usage: tests/run_tests.sh [--ref REF] [--out DIR]
#   REF  commit to test (default HEAD); its own tests/ are the ones run.
#   DIR  where <test>.log/.rc and summary.rc go (default <scratch>/results).
# Tier: fast (stubs + py_compile), budget 60 s. One run at a time (lock).
set -u
ref=HEAD
out=
while [ $# -gt 0 ]; do
    case $1 in
        --ref) ref=${2:?}; shift 2 ;;
        --out) out=${2:?}; shift 2 ;;
        *) echo "usage: $0 [--ref REF] [--out DIR]" >&2; exit 2 ;;
    esac
done
budget=60
per_test=${WUC_TEST_TIMEOUT:-30}
repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel) || exit 2
sha=$(git -C "$repo" rev-parse --verify "$ref^{commit}") || exit 2
tmo=$(command -v timeout || command -v gtimeout) || { echo "need timeout(1)" >&2; exit 2; }

lock=${TMPDIR:-/tmp}/wuc_tests.lock
if ! mkdir "$lock"; then
    echo "another test run holds $lock (pid $(cat "$lock/pid")); not starting" >&2
    exit 75
fi
echo $$ > "$lock/pid"
trap 'rm -f "$lock/pid"; rmdir "$lock"' EXIT

root=$(mktemp -d "${TMPDIR:-/tmp}/wuc_tests.XXXXXX") || exit 2
out=${out:-$root/results}
mkdir -p "$out" "$root/snap" || exit 2
git -C "$repo" archive "$sha" weka_upgrade_checker | tar -x -C "$root/snap" || exit 2
tests=$root/snap/weka_upgrade_checker/tests
echo "ref $sha, scratch $root, results $out, budget ${budget} s (fast tier)"

start=$SECONDS
overall=0
printf 'ref %s\n' "$sha" > "$out/summary.rc"
run_one() {  # run_one <name> <command...>
    local name=$1 rc
    shift
    mkdir -p "$root/tmp/$name"
    "$tmo" "$per_test" "$@" > "$out/$name.log" 2>&1
    rc=$?
    if [ "$rc" -eq 124 ]; then
        echo "TIMEOUT after $per_test s" >> "$out/$name.log"
    fi
    echo "$rc" > "$out/$name.rc"
    printf '%s %s\n' "$name" "$rc" >> "$out/summary.rc"
    printf '%-20s rc=%s  %s\n' "$name" "$rc" "$(tail -n 1 "$out/$name.log")"
    [ "$rc" -eq 0 ] || overall=1
}

# Static check: compiles the checker, runs none of it.
run_one py_compile python3 -I -m py_compile "$root/snap/weka_upgrade_checker/weka_upgrade_checker.py"
for t in "$tests"/test_*.sh; do
    n=$(basename "$t" .sh)
    run_one "$n" "$BASH" "$t" "$root/snap" "$root/tmp/$n"
done
for t in "$tests"/test_*.py; do
    n=$(basename "$t" .py)
    run_one "$n" python3 -I "$t" "$root/snap" "$root/tmp/$n"
done

elapsed=$((SECONDS - start))
printf 'overall %s\nelapsed %s\n' "$overall" "$elapsed" >> "$out/summary.rc"
echo "overall rc=$overall in ${elapsed} s (budget ${budget} s); results in $out"
if [ "$elapsed" -gt $((budget * 2)) ]; then
    echo "WARNING: over twice the ${budget} s budget; find out why before rerunning"
fi
exit "$overall"
