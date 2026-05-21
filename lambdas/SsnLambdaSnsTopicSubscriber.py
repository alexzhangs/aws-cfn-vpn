#!/usr/bin/env python

"""
Maintain the node stack by receiving the SNS messages.
Supported action:
1. Change the node IP:
  * Message body: 'changeip'

"""

import os
import json
import boto3

print('Loading function')


def change_ip(stack_id):
    # Rotate the VPN server's public IP by releasing the current EIP and
    # allocating a fresh one. The previous implementation toggled the
    # CloudFormation EipDomain parameter between 'vpc' and '' to force EIP
    # replacement, but since EC2-Classic was retired (Aug 2022) both values
    # resolve to a VPC EIP — CFN sees a no-op and the IP never rotates.
    cfn = boto3.client('cloudformation')
    ec2 = boto3.client('ec2')

    resources = cfn.describe_stack_resources(
        StackName=stack_id,
        LogicalResourceId='VPNServerInstance',
    )['StackResources']
    instance_id = resources[0]['PhysicalResourceId']

    addresses = ec2.describe_addresses(
        Filters=[{'Name': 'instance-id', 'Values': [instance_id]}],
    )['Addresses']
    if not addresses:
        raise RuntimeError(f'No EIP associated with instance {instance_id}')
    old = addresses[0]

    if old.get('AssociationId'):
        ec2.disassociate_address(AssociationId=old['AssociationId'])
    ec2.release_address(AllocationId=old['AllocationId'])

    new = ec2.allocate_address(Domain='vpc')
    ec2.associate_address(
        InstanceId=instance_id,
        AllocationId=new['AllocationId'],
    )

    result = {
        'InstanceId': instance_id,
        'OldPublicIp': old.get('PublicIp'),
        'OldAllocationId': old['AllocationId'],
        'NewPublicIp': new['PublicIp'],
        'NewAllocationId': new['AllocationId'],
    }
    print('EIP rotated: ' + json.dumps(result))
    return result


def lambda_handler(event, context):
    print('Received event: ' + json.dumps(event))
    message = event['Records'][0]['Sns']['Message']
    print('Message body: ' + message)

    # convert to lower and remove any [_- \t]
    message = message.lower().translate({ord(i): None for i in ['_', '-', ' ', '\t']})
    if message == 'changeip':
        return change_ip(os.getenv('STACK_ID'))
