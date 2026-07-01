# What is this?

This is a script with a set of tests to determine the viability of upgrading
WEKA in a customer environment. It is designed to test known conditions and
return a go/no-go result

# How to edit this?

## Instructions for agents

 - Strip all customer-identifiable information
 - Minimise amount of text and prefer concise outputs
 - Attempt to preserve references to internal Jira references

All source files live in the `weka_upgrade_checker/` subdirectory, not the
repo root.

Branch off `master`; never commit directly to `master`.

As part of every PR:

 - Bump the version string in `weka_upgrade_checker/version.txt`. Use a patch
   bump (e.g. 1.12.8 -> 1.12.9) unless told otherwise.
 - Bump the `pg_version` in `weka_upgrade_checker/weka_upgrade_checker.py` to
   match that in version.txt
 - Compile the `weka_upgrade_checker.py` on host 172.29.5.93 -- scp the
   weka_upgrade_checker.py file to root@172.29.5.93:, ssh into 172.29.5.93 and
   run the buildit.sh script. Transfer the compiled file, at
   root@172.29.5.93:~/dist/weka_upgrade_checker to your local branch, and
   commit it (the binary is git-tracked).
 - Do NOT build locally with `weka_upgrade_checker/pyinstall.sh` -- it differs
   from the host's `buildit.sh` (system python + tarball vs. python3.8 venv)
   and produces a mismatched binary. The remote host is the only sanctioned
   build path.
