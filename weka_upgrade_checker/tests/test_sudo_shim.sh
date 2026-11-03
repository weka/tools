#!/usr/bin/env bash
# The remote sudo() shim (SUDO_SHIM) skips sudo when `id -u` is 0 and
# calls the real sudo otherwise. bash is the only remote login shell covered:
# the checker's other remote commands already need bash.
# Usage: test_sudo_shim.sh <snapshot-dir> <scratch-dir>   (run_tests.sh calls it)
# Needs no host: stub id/sudo on PATH.
set -u
snap=${1:?snapshot dir}
tmp=${2:?scratch dir}
here=$(cd "$(dirname "$0")" && pwd)
stubs=$here/stubs
py=$snap/weka_upgrade_checker/weka_upgrade_checker.py
fails=0
passes=0

check() {  # check <name> <expected> <actual>
    if [ "$2" = "$3" ]; then
        passes=$((passes + 1))
        printf 'PASS %s\n' "$1"
    else
        fails=$((fails + 1))
        printf 'FAIL %s\n  expected: %q\n  actual:   %q\n' "$1" "$2" "$3"
    fi
}

# Read the shim from the checker's source (never retyped here). ast only
# parses the file; nothing in the checker runs.
shim=$(python3 -I - "$py" <<'PY'
import ast, sys
tree = ast.parse(open(sys.argv[1], encoding="utf-8").read())
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "SUDO_SHIM" for t in node.targets
    ):
        print(ast.literal_eval(node.value), end="")
        sys.exit(0)
sys.exit(3)
PY
)
shim_rc=$?
# Without a shim every case below still runs, so a red run shows which
# behaviors fail today, not only that the variable is missing.
check "SUDO_SHIM is a module-level string in the checker" 0 "$shim_rc"

# run_case <shell> <uid> <sudo allow|deny> <command>
# Sets out, err, rc, sudo_calls (the stub sudo's argv lines), id_calls.
run_case() {
    local log=$tmp/stub.log
    : > "$log"
    out=$(PATH="$stubs:/usr/bin:/bin" WUC_STUB_LOG=$log WUC_STUB_UID=$2 \
        WUC_STUB_SUDO=$3 "$1" -c "$shim$4" 2> "$tmp/err")
    rc=$?
    err=$(cat "$tmp/err")
    sudo_calls=$(grep '^sudo ' "$log")
    id_calls=$(grep -c '^id -u' "$log")
}

# POSIX forms the checker's 27 remote calls use: bare, $( ), pipes, if, !,
# loops, a pipe inside $( ), and a raw block that starts with a newline.
forms_name=(bare subst pipe if_false if_true not loop_pipe for subst_pipe
    newline_block exit_status)
forms_cmd=(
    'sudo echo hi'
    'x=$(sudo echo sub); echo "$x"'
    "sudo printf 'a b\\n' | awk '{print \$2}'"
    'if sudo false; then echo T; else echo F; fi'
    'if sudo true; then echo T; else echo F; fi'
    'if ! sudo false; then echo N; fi'
    "printf '1\\n2\\n' | while read -r n; do sudo echo \"n\$n\"; done"
    'for d in a b; do sudo echo "$d"; done'
    'echo "$(sudo printf x | tr x y)"'
    $'\n    if ! sudo false; then\n        echo ok\n    fi\n'
    "sudo sh -c 'exit 3'; echo \"rc=\$?\""
)
forms_out=(hi sub b F T N $'n1\nn2' $'a\nb' y ok rc=3)
# sudo argv each form passes, one line per call (for the non-root user).
forms_sudo=('sudo echo hi' 'sudo echo sub' 'sudo printf a b\n' 'sudo false'
    'sudo true' 'sudo false' $'sudo echo n1\nsudo echo n2'
    $'sudo echo a\nsudo echo b' 'sudo printf x' 'sudo false'
    'sudo sh -c exit 3')

for sh in bash; do  # the only remote login shell the checker supports
    for i in "${!forms_name[@]}"; do
        f=${forms_name[$i]}
        # Root on a host with no sudoers rule for root: same output and exit
        # status, and the stub sudo is never called.
        run_case "/bin/$sh" 0 deny "${forms_cmd[$i]}"
        check "$sh uid0-no-sudoers $f: output" "${forms_out[$i]}" "$out"
        check "$sh uid0-no-sudoers $f: sudo never called" "" "$sudo_calls"
        # A non-root sudo user keeps the same sudo argv and output.
        run_case "/bin/$sh" 1000 allow "${forms_cmd[$i]}"
        check "$sh uid1000 $f: output" "${forms_out[$i]}" "$out"
        check "$sh uid1000 $f: sudo argv unchanged" "${forms_sudo[$i]}" "$sudo_calls"
    done
    # The decision is made on the host by asking id there.
    run_case "/bin/$sh" 0 deny 'sudo true'
    check "$sh uid0: id -u asked on the host" 1 "$id_calls"
    # The shim adds no bytes, so an empty result stays empty.
    check "$sh uid0 sudo true: stdout empty" "" "$out"
    check "$sh uid0 sudo true: stderr empty" "" "$err"
    run_case "/bin/$sh" 1000 allow 'sudo true'
    check "$sh uid1000 sudo true: stdout empty" "" "$out"
    check "$sh uid1000 sudo true: stderr empty" "" "$err"
    # id failing or printing junk must fall through to the real sudo,
    # never run the command as if root.
    for uid in fail '' root 0x0 ' 0' 1+-1; do
        run_case "/bin/$sh" "$uid" deny 'sudo echo hi'
        check "$sh id=[$uid]: command not run without sudo" "" "$out"
        check "$sh id=[$uid]: real sudo called" "sudo echo hi" "$sudo_calls"
    done
done

printf 'SUMMARY test_sudo_shim: %d passed, %d failed\n' "$passes" "$fails"
[ "$fails" -eq 0 ]
