#!/bin/bash
aws lambda invoke \
--function-name=DailySecurityReportSender \
--payload "{\"base_date\": \"$(date +%Y-%m-%d)\"}" \
--cli-binary-format raw-in-base64-out response.json
