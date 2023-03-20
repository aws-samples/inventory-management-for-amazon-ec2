import logging
import os
from dataclasses import dataclass
from typing import List, Dict

import boto3


@dataclass
class SecurityHubFindingDetail:
    SchemaVersion: str
    Id: str
    productArn: str
    productName: str
    CompanyName: str
    Region: str
    GeneratorId: str
    AWSAccountId: str


@dataclass
class SecurityHubDetail:
    findings: List[SecurityHubFindingDetail]


@dataclass
class SecurityHubFindings:
    version: str
    id: str
    detail_type: str
    source: str
    account: str
    time: str
    region: str
    resources: List[str]
    detail: Dict[str, List[Dict]]


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def render_message(security_hub_event: SecurityHubFindings):
    generator_id = security_hub_event.detail["findings"][0]["GeneratorId"]
    command_id, instance_id, *_ = generator_id.split("/")
    ssm_client = boto3.client("ssm")
    command_result = ssm_client.get_command_invocation(CommandId=command_id, InstanceId=instance_id)

    response = f"EC2 Instance CCE Check Result: \n" + \
               f"Resource: {security_hub_event.detail['findings'][0]['Resources'][0]['Id']}\n" + \
               f"Source: {security_hub_event.source}\n" + \
               f"Account: {security_hub_event.account}\n" + \
               f"Region: {security_hub_event.region}\n" + \
               f"Time: {security_hub_event.time}\n" + \
               f"Command Result:\n" + \
               f"{command_result['StandardOutputContent']}\n" + \
               f"Command Detail in Systems Manager: {security_hub_event.detail['findings'][0]['Remediation']['Recommendation']['Url']}"
    return response


def lambda_handler(event, context):
    event["detail_type"] = event.pop("detail-type", "")
    finding = SecurityHubFindings(**event)

    _message = render_message(security_hub_event=finding)
    client = boto3.client("sns")
    client.publish(
        TopicArn=os.environ["TopicArn"],
        Subject=f"[CCE Check] EC2 Instance CCE Result",
        Message=_message,
    )
    logging.info(_message)
