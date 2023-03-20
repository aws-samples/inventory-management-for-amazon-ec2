from aws_cdk import (
    aws_events,
    aws_lambda,
    aws_securityhub,
    aws_events_targets,
    aws_iam,
    aws_sns,
    Stack,
    CfnParameter,
    aws_logs,
    aws_logs_destinations,
)
from constructs import Construct


class InventoryManagementStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        email_address = CfnParameter(
            self,
            "TargetEmail",
            type="String",
            description="The name of the Amazon S3 bucket where uploaded files will be stored.",
        )

        topic_name = "security-alert-event"
        security_hub = aws_securityhub.CfnHub(self, "MyCfnHub")
        self.init_cce_finding_flow(target_log_group="cce-result")
        self.init_cce_finding_notification(email=email_address.value_as_string,
                                           topic_name=topic_name)

    def init_cce_finding_flow(self, target_log_group: str):
        """
        Delivery CCE Finding results from Systems Manager to SecurityHub
        Import Findings:
        Systems Manager -> CloudWatch(target_log_group=cce-result) -> Lambda(ImportCCEFindings) -> SecurityHub

        :param target_log_group:
        :return:
        """
        cce_result = aws_logs.LogGroup(self, target_log_group, log_group_name=target_log_group)
        ssm_importer_lambda = self.init_ssm_to_security_hub_lambda()
        cce_result.add_subscription_filter(
            "CCEFindingFilter",
            destination=aws_logs_destinations.LambdaDestination(ssm_importer_lambda),
            filter_pattern=aws_logs.FilterPattern.all_events()
        )

    def init_cce_finding_notification(self, email, topic_name):
        topic = aws_sns.Topic(self, "CCEFindingTopic", topic_name=topic_name)
        aws_sns.Subscription(
            self,
            "CCEFindingResult",
            topic=topic,
            endpoint=email,
            protocol=aws_sns.SubscriptionProtocol.EMAIL,
        )
        email_parser = self.init_notify_findings_lambda(sns_topic=topic)

        _event_pattern = {
            "source": ["aws.securityhub"],
            "detail": {
                "findings": {
                    "Types": ["Common Configuration Checks/Vulnerabilities/CCE"]
                }
            }
        }
        _rule = aws_events.Rule(
            self, "CCEFindingRule", event_pattern=aws_events.EventPattern(**_event_pattern),
            rule_name="CCEFindingRule"
        )
        _rule.add_target(target=aws_events_targets.LambdaFunction(handler=email_parser))

    def init_notify_findings_lambda(self, sns_topic):
        """
        Parser for CCE Findings from CloudWatch
        :param sns_topic:
        :return:
        """
        event_policy = aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            resources=["*"],
            actions=["events:PutEvents", "sns:Publish"],
        )
        ssm_policy = aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            resources=["*"],
            actions=["ssm:GetCommandInvocation"]
        )
        lambda_event_parser = aws_lambda.Function(
            self,
            "NotifyCCEFindings",
            function_name="NotifyCCEFindings",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            handler="notify_cce_result.lambda_handler",
            code=aws_lambda.Code.from_asset("source/securityhub"),
            environment={"TopicArn": sns_topic.topic_arn},
        )
        lambda_event_parser.add_to_role_policy(event_policy)
        lambda_event_parser.add_to_role_policy(ssm_policy)
        return lambda_event_parser

    def init_ssm_to_security_hub_lambda(self):
        lambda_policy = aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            resources=["*"],
            actions=["ec2:Describe*", "securityhub:*"],
        )
        lambda_event_parser = aws_lambda.Function(
            self,
            "ImportCCEFindings",
            function_name="ImportCCEFindings",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            handler="import_cce_findings.lambda_handler",
            code=aws_lambda.Code.from_asset("source/securityhub")
        )
        lambda_event_parser.add_to_role_policy(lambda_policy)
        return lambda_event_parser
