#!/usr/bin/env python3
"""Skipping sudo as root, through the checker's own code: run_command's shim
prefix (including the next-address retry) and the two local service calls.

Usage: python3 -I test_sudo_python.py <snapshot-dir> <scratch-dir>
Each case runs in a fresh child process that patches os.geteuid before it
imports the snapshot, so a module-level SUDO list sees the patched uid. The
import runs with cwd = scratch (the checker truncates ./weka_upgrade_checker.log),
stub packaging/pkg_resources (no pip) and sockets that refuse to connect.
Remote calls go to the stub ssh, which runs the command locally under bash.
"""
import json
import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUBS = os.path.join(HERE, "stubs")
CASES = ["local_root", "local_user", "remote_retry_root", "remote_json_root",
         "remote_call_root", "remote_user"]


def load_checker(snap, euid):
    os.geteuid = lambda: euid

    def no_network(*args, **kwargs):
        raise RuntimeError("test blocked a network connection")

    socket.socket.connect = no_network
    socket.create_connection = no_network
    sys.path.insert(0, os.path.join(HERE, "pystubs"))
    import importlib.util
    path = os.path.join(snap, "weka_upgrade_checker", "weka_upgrade_checker.py")
    spec = importlib.util.spec_from_file_location("wuc_snapshot", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def child(case, snap, tmp):
    os.chdir(tmp)
    log = os.path.join(tmp, "stub.log")
    open(log, "w").close()
    os.environ.update(PATH=STUBS + ":/usr/bin:/bin", WUC_STUB_LOG=log,
                      WUC_STUB_SHELL="/bin/bash", WUC_STUB_SSH_FAIL="addr-a")
    root = case.endswith("_root")
    os.environ["WUC_STUB_UID"] = "0" if root else "1000"
    os.environ["WUC_STUB_SUDO"] = "deny" if root else "allow"
    mod = load_checker(snap, 0 if root else 1000)
    shim = getattr(mod, "SUDO_SHIM", None)
    got = {"shim_defined": isinstance(shim, str) and shim != ""}

    if case.startswith("local"):
        calls = []

        def fake_call(argv, **kwargs):
            calls.append(argv)
            return 1  # both probes "fail", so both argv lists are recorded

        subprocess.call = fake_call
        try:
            mod.weka_cluster_checks("0.0.0")
        except SystemExit:
            pass
        got["local_argv"] = calls
    else:
        cmd = {"remote_json_root": "sudo printf '{\"a\": 1}'",
               "remote_call_root": "sudo true"}.get(
            case, 'x=$(sudo echo hi); echo "$x"')
        host = {"ip": "addr-a", "hostname": "host-b"}
        kwargs = {"remote_json_root": {"use_check_output": False, "use_json": True},
                  "remote_call_root": {"use_check_output": False, "use_call": True}
                  }.get(case, {"use_check_output": True})
        results = mod.parallel_execution([host], [cmd], **kwargs)
        lines = open(log).read().splitlines()
        sent = []
        for n in range(1, 1 + sum(1 for l in lines if l.startswith("ssh "))):
            with open(f"{log}.ssh_cmd.{n}") as f:
                sent.append(f.read())
        got.update(results=[list(r) for r in results],
                   ssh=[l for l in lines if l.startswith("ssh ")],
                   sudo=[l for l in lines if l.startswith("sudo ")],
                   prefixed_once=[s == (shim or "") + cmd and bool(shim) for s in sent],
                   ssh_target=host.get("ssh_target"))
    print(json.dumps(got))


EXPECT = {
    "local_root": {"local_argv": [["service", "weka-agent", "status"],
                                  ["systemctl", "status", "weka-agent"]]},
    "local_user": {"local_argv": [["sudo", "service", "weka-agent", "status"],
                                  ["sudo", "systemctl", "status", "weka-agent"]]},
    # Root, no sudoers rule: the first address fails (255) and the retry on
    # the hostname also carries the shim exactly once.
    "remote_retry_root": {"results": [["host-b", "hi"]], "sudo": [],
                          "ssh": ["ssh addr-a", "ssh host-b"],
                          "prefixed_once": [True, True], "ssh_target": "host-b"},
    "remote_json_root": {"results": [["host-b", {"a": 1}]], "sudo": [],
                         "prefixed_once": [True, True]},
    "remote_call_root": {"results": [["host-b", 0]], "sudo": [],
                         "prefixed_once": [True, True]},
    # A non-root sudo user still goes through the real sudo, same argv.
    "remote_user": {"results": [["host-b", "hi"]], "sudo": ["sudo echo hi"],
                    "prefixed_once": [True, True]},
}


def main(snap, tmp):
    fails = passes = 0
    for case in CASES:
        ctmp = os.path.join(tmp, case)
        os.makedirs(ctmp)
        proc = subprocess.run([sys.executable, "-I", __file__, "--child", case, snap, ctmp],
                              capture_output=True, text=True, timeout=30)
        with open(os.path.join(ctmp, "child.out"), "w") as f:
            f.write(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
        try:
            got = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            got = {"child_error": f"rc={proc.returncode}, see {ctmp}/child.out"}
        expect = dict(EXPECT[case], shim_defined=True)
        if case.startswith("local"):
            expect.pop("shim_defined")  # the local fix doesn't need the shim
        for key, want in expect.items():
            have = got.get(key, got.get("child_error", "<missing>"))
            if have == want:
                passes += 1
                print(f"PASS {case} {key}")
            else:
                fails += 1
                print(f"FAIL {case} {key}\n  expected: {want!r}\n  actual:   {have!r}")
    print(f"SUMMARY test_sudo_python: {passes} passed, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(*sys.argv[2:5])
    else:
        sys.exit(main(*sys.argv[1:3]))
