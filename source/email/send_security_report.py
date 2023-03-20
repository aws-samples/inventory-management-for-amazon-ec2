import datetime
import json
import os
from collections import defaultdict

import boto3
from botocore.exceptions import ClientError


def get_default_severity():
    _finding = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFORMATIONAL": 0}
    return _finding


def aggregate_findings(findings) -> list:
    summary = {
        k: defaultdict(get_default_severity)
        for k in ["regions", "accounts", "product", "company", "types", "resources"]
    }

    # aggregate data
    for f in findings:
        summary["regions"][f["Region"]][f["Severity"]["Label"]] += 1
        summary["accounts"][f["AwsAccountId"]][f["Severity"]["Label"]] += 1
        summary["product"][f["ProductName"]][f["Severity"]["Label"]] += 1
        summary["company"][f["CompanyName"]][f["Severity"]["Label"]] += 1
        summary["types"][f["Types"][0].split("/")[-1]][f["Severity"]["Label"]] += 1
        summary["resources"][f["Resources"][0]["Type"]][f["Severity"]["Label"]] += 1

    # serialize data
    table_data = []
    for table_name, data in summary.items():
        row = []

        for k, sev_count in data.items():
            row.append({"row_name": k, **sev_count})

        table_data.append({
            "table_name": table_name, "rows": row
        })
    return table_data


EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
AWS_REGION = os.environ["REGION"]
SENDER = f"SecurityAdmin<{EMAIL_ADDRESS}>"
RECIPIENT = EMAIL_ADDRESS
CONFIGURATION_SET = os.environ["CONFIG_SET"]
TEMPLATE_NAME = os.environ["TEMPLATE_NAME"]


def send_security_report(template_data):
    # Create a new SES resource and specify a region.
    client = boto3.client('ses', region_name=AWS_REGION)

    # Try to send the email.
    try:
        # Provide the contents of the email.
        response = client.send_templated_email(
            Source=SENDER,
            Destination={
                'ToAddresses': [
                    RECIPIENT,
                ],
            },
            ConfigurationSetName=CONFIGURATION_SET,
            Template=TEMPLATE_NAME,
            TemplateData=json.dumps(template_data)
        )
    # Display an error if something goes wrong.
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])


def lambda_handler(event, context):
    securityhub = boto3.client("securityhub")
    finding_iterator = securityhub.get_paginator('get_findings')
    findings = []

    base_date = event.get("base_date")

    if base_date is None:
        today = datetime.datetime.now()
        yesterday = today - datetime.timedelta(days=1)
        base_date = yesterday.strftime("%Y-%m-%d")

    for f in finding_iterator.paginate(Filters={
        "CreatedAt": [{
            "Start": base_date,
            "End": base_date
        }]
    }):
        findings += f["Findings"]
    aggregated_summary = aggregate_findings(findings=findings)
    template_data = {"meta": {"date": base_date, "total": len(findings)},
                     "tables": aggregated_summary}
    send_security_report(template_data=template_data)
    return aggregated_summary
