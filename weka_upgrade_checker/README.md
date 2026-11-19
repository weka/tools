# weka_upgrade_checker
WEKA Upgrade Checker

The script takes into account all of the best practices requirements for upgrades.

It is recommended that the upgrade checker be ran 24 hours in advance, so that all issues can be resolved prior to the planned upgrade window.


## Prior to running the script follow the prerequisites listed below:

1. The script should be run on a backend WEKA host
2. You should have either sudo access or be root. On AWS systems it is usually easier to be logged in as ec2-user.
3. Your user should be logged to WEKA, such that `weka status` etc work
4. Passwordless SSH should be configured prior to starting.

[Github link](https://github.com/weka/tools/tree/master/weka_upgrade_checker)

To download directly to a host, with internet access, make the script executable and show syntax help, run:

```bash
curl -LO https://github.com/weka/tools/raw/master/weka_upgrade_checker/weka_upgrade_checker.py
python3.8 ./weka_upgrade_checker.py
```

## Exit code

The checker exits 1 when any check failed and 0 when there are only warnings, so a runbook or automation can gate on it. A failed prerequisite (not logged in, no SSH, invalid target version) also exits 1.

## JSON output

`--json <file>` also writes the result of every check to `<file>`: the checker, source and target versions, the pass/warn/fail counts, and one record per check with a stable `id` (from the check's section heading), its `verdict` (`pass`, `warn` or `fail`), the per-host sub-heading as `detail` when there is one, and the `message`. The file is written on every exit, including a check that stops the run early.

## Known issues

`known_issues.json` lists defects bound to a WEKA version. Each entry is matched against the upgrade path:

- `affected_versions`: ranges of the versions the upgrade goes to (every hop after the source). A range is `[min, max)`; an empty `max` covers the rest of `min`'s release line.
- `source_versions`: ranges of the version a hop starts from (the source, then each intermediate version). With `affected_versions` too, both must match for the same hop; on its own, the issue is reported on every hop that leaves a matching version.
- `version_from`: the issue applies to an upgrade that crosses this version.
- `related_protocols`, `link_types`, `obj_store` and `multi_org` limit an entry to clusters that use them.
