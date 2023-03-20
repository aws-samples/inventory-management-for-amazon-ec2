#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.inventory_management_stack import InventoryManagementStack
from stacks.secuirty_report_stack import DailyEmailReportStack
from stacks.vpc_setup_stack import VPCSetupStack

app = cdk.App()
VPCSetupStack(app, "DemoVPCStack")
InventoryManagementStack(app, "InventoryManagementStack")
DailyEmailReportStack(app, "DailyEmailReportStack")
app.synth()
