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


def change_ip(stack):
    new_param = []
    for p in stack.parameters:
        if p['ParameterKey'] == 'EipDomain':
            p['ParameterValue'] = 'vpc' if p['ParameterValue'] == '' else ''
            p['UsePreviousValue'] = False
        else:
            p.pop('ParameterValue')
            p['UsePreviousValue'] = True
        new_param.append(p)

    return stack.update(
        UsePreviousTemplate=True,
        Parameters=new_param,
        Capabilities=[
            'CAPABILITY_IAM',
            'CAPABILITY_NAMED_IAM'
        ]
    )


def lambda_handler(event, context):
    print('Received event: ' + json.dumps(event))
    message = event['Records'][0]['Sns']['Message']
    print('Message body: ' + message)

    cfn = boto3.resource('cloudformation')
    stack = cfn.Stack(os.getenv('STACK_ID'))

    # convert to lower and remove any [_- \t]
    message = message.lower().translate({ord(i): None for i in ['_', '-', ' ', '\t']})
    if message == 'changeip':
        return change_ip(stack)
