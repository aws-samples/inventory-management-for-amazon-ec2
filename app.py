#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.vpc_setup_stack import VPCSetupStack

app = cdk.App()
VPCSetupStack(app, "DemoVPCStack")
app.synth()
