import aws_cdk as cdk
import aws_cdk.aws_autoscaling as autos
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
from aws_cdk import (
    aws_kms as kms,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
    aws_ec2 as ec2,
    aws_iam as iam,
    Stack,
    NestedStack,
)
from constructs import Construct


class VPCSetupStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.vpc = self.init_vpc()
        self.set_vpc_service_endpoints(vpc=self.vpc)
        dev_tag_dic = {
            "isPublic": "true",
            "InventoryCategory": "WAS",
            "Env": "Dev",
            "HandlePI": "N",
            "Project": "InventoryManagement",
        }
        prod_tag_dic = {
            "isPublic": "true",
            "InventoryCategory": "WAS",
            "Env": "Prod",
            "HandlePI": "N",
            "Project": "InventoryManagement",
        }

        session_key = kms.Key(self, "-ssm-session-key", alias="ssm-session-key")
        WASStack(self, "DevWAS", vpc=self.vpc, session_key=session_key, tags=dev_tag_dic, prefix="DEV")
        WASStack(self, "ProdWAS", vpc=self.vpc, session_key=session_key, tags=prod_tag_dic, prefix="PROD")

    def init_vpc(self) -> ec2.Vpc:
        public_subnet = ec2.SubnetConfiguration(
            subnet_type=ec2.SubnetType.PUBLIC, name="PublicSubnet", cidr_mask=25
        )
        private_subnet = ec2.SubnetConfiguration(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            name="PrivateSubnet",
            cidr_mask=25,
        )
        _vpc = ec2.Vpc(
            self,
            "VPC",
            ip_addresses=ec2.IpAddresses.cidr("10.100.0.0/16"),
            nat_gateways=2,
            max_azs=2,
            subnet_configuration=[public_subnet, private_subnet],
        )
        return _vpc

    def set_vpc_service_endpoints(self, vpc: ec2.Vpc):
        vpc.add_interface_endpoint(
            "SSMEndpoint", service=ec2.InterfaceVpcEndpointAwsService.SSM
        )
        vpc.add_interface_endpoint(
            "SSMSessionEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
        )


class WASStack(NestedStack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            vpc: ec2.Vpc,
            session_key: kms.Key,
            tags: dict,
            prefix="",
            **kwargs
    ):
        super().__init__(scope, construct_id, **kwargs)
        self.vpc = vpc
        self.session_key = session_key
        self.bucket = s3.Bucket(self, "S3")
        self.upload_code_to_s3(bucket=self.bucket)
        self.init_was_workload(tags=tags, prefix=prefix)

    @property
    def instance_type(self):
        instance_size = ec2.InstanceSize.SMALL
        instance_class = ec2.InstanceClass.T3
        instance_type = ec2.InstanceType.of(
            instance_class=instance_class, instance_size=instance_size
        )
        return instance_type

    def upload_code_to_s3(self, bucket):
        s3_deploy.BucketDeployment(
            self,
            "CopyCode",
            sources=[s3_deploy.Source.asset("source/")],
            destination_bucket=bucket,
        )

    def get_ec2_user_data(self) -> ec2.UserData:
        user_data = ec2.UserData.for_linux()
        user_data.add_s3_download_command(
            bucket=self.bucket,
            bucket_key="server/webapp.py",
            local_file="/home/ec2-user/server/",
        )
        commands = [
            "yum update -y",
            "pip install flask",
            "python /home/ec2-user/server/webapp.py > /home/ec2-user/server/was.log 2>&1",
        ]
        user_data.add_commands(*commands)
        return user_data

    def init_was_workload(self, tags: dict = None, prefix=""):
        if tags is None:
            tags = {}

        alb_sg = self.set_alb_security_group(vpc=self.vpc, prefix=prefix)
        was_sg = self.set_was_security_group(
            vpc=self.vpc, alb_security_group=alb_sg, prefix=prefix
        )
        launch_template = self.init_launch_template(
            security_group=was_sg, tags=tags, prefix=prefix
        )
        asg = self.init_was_auto_scaling_group(
            vpc=self.vpc,
            launch_template=launch_template,
            prefix=prefix,
        )
        alb = self.init_application_load_balancer(
            vpc=self.vpc, alb_sg=alb_sg, auto_scaling_group=asg, prefix=prefix
        )
        self.set_scale_policy(asg=asg, prefix=prefix)

        cdk.CfnOutput(
            self,
            prefix + "ALBDNS",
            description="Public DNS entry point",
            value=alb.load_balancer_dns_name,
        )
        return alb

    def set_alb_security_group(self, vpc, prefix=""):
        alb_sg = ec2.SecurityGroup(self, "WAS-ALB-SG", vpc=vpc, allow_all_outbound=True)
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), connection=ec2.Port.tcp(80))
        return alb_sg

    def set_was_security_group(self, vpc: ec2.Vpc, alb_security_group, prefix=""):
        was_sg = ec2.SecurityGroup(self, "WAS-APP-SG", vpc=vpc, allow_all_outbound=True)
        was_sg.add_ingress_rule(alb_security_group, connection=ec2.Port.tcp(80))
        was_sg.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), connection=ec2.Port.tcp(443))
        return was_sg

    def init_launch_template(
            self, security_group, tags: dict, prefix=""
    ) -> ec2.LaunchTemplate:

        machine_image = ec2.MachineImage.latest_amazon_linux()
        ssm_role = iam.Role(
            self,
            prefix + "WASInstanceRole",
            role_name=prefix + "WASInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonS3FullAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                )
            ],
            inline_policies={
                "DecryptKMS": iam.PolicyDocument(
                    statements=[iam.PolicyStatement(actions=["kms:Decrypt"], resources=[self.session_key.key_arn])]
                )})
        launch_template = ec2.LaunchTemplate(
            self,
            prefix + "Instance",
            instance_type=self.instance_type,
            machine_image=machine_image,
            role=ssm_role,
            security_group=security_group,
            user_data=self.get_ec2_user_data(),
            detailed_monitoring=True,
        )
        for k, v in tags.items():
            cdk.Tags.of(launch_template).add(k, v)
        return launch_template

    def init_was_auto_scaling_group(
            self,
            vpc,
            launch_template,
            prefix="",
    ) -> autos.AutoScalingGroup:
        auto_scaling_group = autos.AutoScalingGroup(
            self,
            prefix + "ASG",
            launch_template=launch_template,
            min_capacity=2,  # min 2 EC2 needed
            max_capacity=4,  # max 4 EC2 running in case of workload increase
            desired_capacity=2,  # always keep two EC2 running (one per AZ)
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            health_check=autos.HealthCheck.ec2(grace=cdk.Duration.seconds(120)),
        )
        return auto_scaling_group

    def init_application_load_balancer(self, vpc, alb_sg, auto_scaling_group, prefix=""):
        alb = elbv2.ApplicationLoadBalancer(
            self,
            prefix + "ALB",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg
        )
        listener = alb.add_listener(prefix + "Listener", port=80, open=True)
        listener.add_targets(prefix + "Fleet", port=80, targets=[auto_scaling_group])
        return alb

    def set_scale_policy(self, asg: autos.AutoScalingGroup, prefix=""):
        # set AutoScaling Policy
        asg.scale_on_request_count(
            prefix + "RequestUtilization",
            target_requests_per_minute=100,
            cooldown=cdk.Duration.seconds(60),
            estimated_instance_warmup=cdk.Duration.seconds(120),
        )
