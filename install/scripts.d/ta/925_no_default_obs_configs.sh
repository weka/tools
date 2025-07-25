#!/bin/bash

set -ueo pipefail # Fail with an error code if there's any sub-command/variable error

DESCRIPTION="Default OBS tiering configuration"
JIRA_REFERENCE="WEKAPP-501288"
SCRIPT_TYPE="single"

RETURN_CODE=0

# Check if we can run weka commands
weka status &> /dev/null
RC=$?

case ${RC} in
    254)
        echo "ERROR: Not able to run weka commands."
        exit 254
        ;;
    127)
        echo "WEKA not found."
        exit 254
        ;;
    41)
        echo "Unable to login to Weka cluster."
        exit 254
        ;;
esac

DEFAULT_OBS_CONFIGURATION="^_mbps: 4294967295 _mbps: 4294967295 _mbps: 4294967295 64 64 64 N/A$"
if [[ $(weka fs tier s3  -o downloadBandwidth,uploadBandwidth,removeBandwidth,downloads,uploads,removals,maxUploadExtents,maxUploadSize --no-header | sed 's/  */ /g' | grep "${DEFAULT_OBS_CONFIGURATION}" | wc -l) -ge 1 ]]; then
    echo "WARN: S3 Tiering targets (OBS Buckets) have been detected with the default performance figures"
    echo " This suggests no S3 performance tuning has been done. While this can be completely fine,"
    echo " some S3 tiering targets can experience performance problems with the default configuration,"
    echo " and require tuning to e.g. reduce the number of concurrent connections"
    echo "Recommended steps: monitor S3 tiering performance, especially if the cluster is in backpressure"
    echo "  If performance is problematic, review the S3 provider's recommendations for concurrent connections etc"
    RETURN_CODE=254
else
    echo "No default OBS performance profiles shown, either it's set specifically or no OBS is in use"
fi

exit ${RETURN_CODE}
