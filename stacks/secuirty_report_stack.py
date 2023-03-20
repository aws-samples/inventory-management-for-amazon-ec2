from aws_cdk import (
    aws_lambda,
    aws_events_targets,
    aws_iam,
    aws_ses as ses,
    Stack,
    CfnParameter,
)
from aws_cdk.aws_events import Rule, Schedule
from constructs import Construct


class DailyEmailReportStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.email_address = CfnParameter(
            self,
            "TargetEmail",
            type="String",
            default="taekyung@amazon.com",
            description="Target Email Address",
        )
        with open("source/email/daily_security_report_template.html") as f:
            html_part = f.read()
        self.email_template = ses.CfnTemplate(self, "SecurityEmailTemplate",
                                              template=ses.CfnTemplate.TemplateProperty(
                                                  subject_part="Daily Security Report",
                                                  html_part=html_part,
                                                  text_part="Security Report sent by Email",
                                                  template_name="DailySecurityEmailTemplate")
                                              )
        self.configuration_set = ses.ConfigurationSet(self, "DefaultConfigurationSet",
                                                      configuration_set_name="DefaultConfigSet")
        self.identity = ses.CfnEmailIdentity(self, "EmailIdentity", email_identity=self.email_address.value_as_string)

        lambda_report_sender = self.create_template_render()
        report_schedule_rule = Rule(self, "SecurityReportSchedule",
                                    rule_name="SecurityReportSchedule",
                                    schedule=Schedule.cron(hour="18", minute="0"))
        report_schedule_rule.add_target(aws_events_targets.LambdaFunction(
            lambda_report_sender))

    def create_template_render(self) -> aws_lambda.Function:
        email_sender_policy = aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            resources=["*"],
            actions=["ses:SendTemplatedEmail"],
        )
        read_security_hub_policy = aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            resources=["*"],
            actions=["securityhub:Get*"],
        )
        lambda_email_renderer = aws_lambda.Function(
            self,
            "SendDailyReportPolicy",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            handler="send_security_report.lambda_handler",
            code=aws_lambda.Code.from_asset("source/email"),
            function_name="DailySecurityReportSender",
            environment={
                "EMAIL_ADDRESS": self.email_address.value_as_string,
                "CONFIG_SET": self.configuration_set.configuration_set_name,
                "REGION": "ap-northeast-2",
                "TEMPLATE_NAME": self.email_template.template.template_name
            }
        )
        lambda_email_renderer.add_to_role_policy(email_sender_policy)
        lambda_email_renderer.add_to_role_policy(read_security_hub_policy)
        return lambda_email_renderer
