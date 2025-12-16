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
