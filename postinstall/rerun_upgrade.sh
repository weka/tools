#!/bin/sh

set -ue

value=$(weka debug config show upgradeInfo.fsABISignature | sed s/[^0-9]//g)

case "$value" in
  3304026876215939436)
    echo "Supported version v447 \ v4481 \ v4482"
    ;;
  6645710715516825926)
    echo "Supported version v4411"
    ;;
  9173821532638213258)
    echo "Supported version v446"
    ;;
  14024210421467651195)
    echo "Supported version v430 \ v431 \ v432 \ v433 \ v435 \ v440 \ v441 \ v442 \ v443 \ v444 \ v445 \ v4451 \ v4452"
    ;;
  14281639603829773483)
    echo "Supported version v420 \ v4211 \ v4213 \ v4215 \ v4216 \ v4217 \ v4218 \ v427"
    ;;
  16219299941972660884)
    echo "Supported version v449"
    ;;
  *)
    echo "Unsupported version"
    exit 1
    ;;
esac

echo "Resetting version"
weka debug config override upgradeInfo.fsABISignature 0xc632938d646c94ab

echo "Rerunning upgrade task"
weka debug manhole --leader start_block_upgrade_task
