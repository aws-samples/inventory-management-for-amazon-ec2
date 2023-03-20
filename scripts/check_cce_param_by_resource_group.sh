#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [ $# -ne 1 ]; then
  echo "Usage: $0 TARGET_RESOURCE_GROUP_NAME"
  exit
else
  TARGET_RESOURCE_GROUP=$1
  echo "Run CCE Check, TargetResourceGroup=$TARGET_RESOURCE_GROUP"
fi

aws ssm send-command --document-name "AWS-RunShellScript" --document-version "1" \
--targets "[{\"Key\":\"resource-groups:Name\",\"Values\":[\"$TARGET_RESOURCE_GROUP\"]}]" \
--parameters "$(cat $SCRIPT_DIR/cce_check_commands.json)" \
--timeout-seconds 600 --max-concurrency "50" --max-errors "0" \
--output-s3-bucket-name "inventory-demo-cce" \
--cloud-watch-output-config '{"CloudWatchLogGroupName":"cce-result","CloudWatchOutputEnabled":true}' \
--region ap-northeast-2