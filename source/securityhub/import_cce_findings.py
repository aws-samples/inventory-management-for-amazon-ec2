import datetime
import json
import uuid
import zlib
from base64 import b64decode
from dataclasses import dataclass
from typing import List

import boto3

REGION = "ap-northeast-2"


@dataclass
class CloudWatchResponseEvent:
    id: str
    timestamp: int
    message: str


@dataclass
class CloudWatchResponse:
    messageType: str
    owner: str
    logGroup: str
    logStream: str
    subscriptionFilters: list
    logEvents: List[CloudWatchResponseEvent]


@dataclass
class Finding:
    Title: str
    SchemaVersion: str
    Severity: dict
    Types: List[str]
    AwsAccountId: str
    CreatedAt: str
    UpdatedAt: str
    Description: str
    GeneratorId: str
    Id: ""
    ProductArn: ""
    Resources: []
    Remediation: dict

    @staticmethod
    def get_arn(service, region, account_id):
        return f"arn:aws:{service}:{region}:{account_id}:product/{account_id}/default"


def decode(data):
    compressed_payload = b64decode(data)
    json_payload = zlib.decompress(compressed_payload, 16 + zlib.MAX_WBITS)
    return json.loads(json_payload)


def import_cce_finding(watch_response: CloudWatchResponse):
    now = datetime.datetime.fromtimestamp(watch_response.logEvents[0]["timestamp"] / 1000)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    command_id, instance_id, *_ = watch_response.logStream.split("/")
    run_command_url = f"https://{REGION}.console.aws.amazon.com/systems-manager/run-command/{command_id}?region={REGION}"

    finding = Finding(
        Title="CCE(Common Configuration Error) Check result by SSM",
        SchemaVersion="2018-10-08",
        Severity={
            "Label": "INFORMATIONAL",
            "Original": "0"
        },
        Types=[
            "Common Configuration Checks/Vulnerabilities/CCE"
        ],
        Id=uuid.uuid4().hex,
        GeneratorId=watch_response.logStream,
        AwsAccountId=watch_response.owner,
        Description="CCE(Common Configuration Error) Vulnerabilities defined on SystemsManager RunCommand",
        CreatedAt=now_str, UpdatedAt=now_str,
        ProductArn=Finding.get_arn(service="securityhub", account_id=watch_response.owner, region=REGION),
        Resources=[
            {
                "Type": "AwsEc2Instance",
                "Id": f"arn:aws:ec2:{REGION}:{watch_response.owner}:instance/{instance_id}"
            }
        ],
        Remediation={
            "Recommendation": {
                "Text": "Check the results in Systems Manager",
                "Url": run_command_url
            },
        },
    )

    securityhub_client = boto3.client('securityhub')
    resp = securityhub_client.batch_import_findings(Findings=[finding.__dict__])
    return resp


def lambda_handler(event, context):
    response = decode(event['awslogs']['data'])
    watch_response = CloudWatchResponse(**response)
    return import_cce_finding(watch_response=watch_response)
