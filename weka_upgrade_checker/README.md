# weka_upgrade_checker
Weka Upgrade Checker

The script takes into account all of the best practices requirements outlined in the document for upgrade best practices.

It is recommended that the pre-upgrade checker be run 24hrs in advance so that all issues can be resolved prior to the planned upgrade window.


## Prior to running the script follow the prerequisites listed below:

1. The script should be run on a backend weka host
2. You should have either sudo access or be root. On AWS systems it's usually easier to be ec2-user
3. Your user should be logged to WEKA, such that `weka status` etc work
4. Passwordless SSH should be configured prior to starting.

[Github link](https://github.com/weka/tools/tree/master/weka_upgrade_checker)

To download directly to a host with Internet access (into current directory), make the script executable, and show syntax help:

```bash
curl -LO https://github.com/weka/tools/raw/master/weka_upgrade_checker/weka_upgrade_checker.py
python3.8 ./weka_upgrade_checker.py
```
