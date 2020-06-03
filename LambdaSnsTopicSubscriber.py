#!/usr/bin/env python

# Description:
#   Receive AWS Config events through SNS, and update Domain, Node and SSManager
#   in shadowsocks-manager.

import os, json
import boto3, botocore.vendored.requests as requests

print('Loading function')

def call_ssm(**kwargs):
    client = boto3.client('lambda')
    resp = client.invoke(
        FunctionName=os.getenv('LAMBDA_SSM_API_ARN'),
        Payload=json.dumps(kwargs))
    if resp['StatusCode'] >= 400:
        raise Exception('Failed to call the Lambda of SSM API. Response: ' + resp)
    func_resp = json.load(resp['Payload'])
    if func_resp and isinstance(func_resp, dict) and func_resp.get('errorMessage'):
        return None
    return func_resp

def lambda_handler(event, context):
    print('Received event: ' + json.dumps(event))
    msg = event['Records'][0]['Sns']['Message']
    print('Message body: ' + msg)

    try:
        ccnm = CCNM(json.loads(msg))
    except Exception as e:
        print(str(e))
        return

    if ccnm.rtype != 'AWS::EC2::Instance':
        print('Skip message request type: ' + ccnm.rtype)
        return

    if not ccnm.is_vpn_instance():
        print('Skip none VPN instance.')
        return

    node_name = ccnm.get_tag(name='Name')
    if node_name:
        node = dict(
            name=node_name,
            public_ip=ccnm.resource['publicIpAddress'],
            private_ip=ccnm.resource['privateIpAddress'],
            location=get_long_region_name(ccnm.MCI['awsRegion']),
            is_active=(ccnm.resource['state']['name'] == 'running'),
            sns_endpoint=ccnm.get_tag(name='SnsTopicArn'),
            sns_access_key=ccnm.get_tag(name='AccessKeyForUserSnsPublisher'),
            sns_secret_key=ccnm.get_tag(name='SecretKeyForUserSnsPublisher'))
    else:
        print('There is no tag with name "Name" on the instance. Skip to update Domain, Node and SSManager in shadowsocks-manager.')
        return

    domain_obj_str = ccnm.get_tag(name='Domain')
    if domain_obj_str:
        domain = json.loads(domain_obj_str)
        domains = call_ssm(action='list', model='Domain', filter=dict(name=domain['name']))
        if domains:
            domain = domains[0]
        else:
            domain = call_ssm(action='save', model='Domain', data=domain)
        node['domain'] = domain['id']
    else:
        print('There is no tag with name "Domain" on the instance. Skip to update Domain in shadowsocks-manager.')
        domain = None

    nodes = call_ssm(action='list', model='Node', filter=dict(name=node['name']))
    if nodes:
        node['id'] = nodes[0]['id']

    if ccnm.ctype == 'CREATE':
        node = call_ssm(action='save', model='Node', data=node)
    elif ccnm.ctype == 'UPDATE':
        if nodes:
            fields = []
            if ccnm.is_changed(name='Configuration.PublicIpAddress'):
                fields.append('public_ip')
            if ccnm.is_changed(name='Configuration.State.Name'):
                fields.append('is_active')
            if fields:
                node = call_ssm(action='save', model='Node', method='PATCH', data=node, fields=fields)
            else:
                print('no need to update node.')
        else:
            node = call_ssm(action='save', model='Node', data=node)
    elif ccnm.ctype == 'DELETE':
        if nodes:
            node['is_active'] = False
            node = call_ssm(action='save', model='Node', method='PATCH', data=node, fields=['is_active'])
    else:
        print('Skip unsupported change type' + self.ctype)
        return

    ssm_obj_str = ccnm.get_tag(name='SSManager')
    if ssm_obj_str:
        ssm = json.loads(ssm_obj_str)
        ssm['node'] = node['id']
        ssms = call_ssm(action='list', model='SSManager', filter=dict(node=node['id']))
        if ssms:
            ssm = ssms[0]
        else:
            ssm = call_ssm(action='save', model='SSManager', data=ssm)
    else:
        print('There is no tag with name "Domain" on the instance. Skip to update SSManager in shadowsocks-manager.')
        ssm = None

    return {
        "node": node,
        "domain": domain if domain else None,
        "ssm": ssm if ssm else None
    }

def get_long_region_name(region):
    # get the long name of AWS region
    client = boto3.client('ssm')
    resp = client.get_parameter(Name='/aws/service/global-infrastructure/regions/{region}/longName'.format(region=region))
    return resp['Parameter']['Value']

class CCNM(object):
    # Configuration Item Change Notification Message

    def __init__(self, msg):
        if not isinstance(msg, dict):
            raise TypeError('{} is not a Dict.'.format(type(msg)))

        self.msg = msg
        self.mtype = msg.get('messageType', None)
        if self.mtype != 'ConfigurationItemChangeNotification':
            raise ValueError('{} is not ConfigurationItemChangeNotification message.'.format(self.mtype))

        self.MCID = msg['configurationItemDiff']
        self.MCI = msg['configurationItem']
        self.ctype = self.MCID['changeType']
        self.rtype = self.MCI['resourceType']
        if self.ctype in ['CREATE', 'UPDATE']:
            self.resource = self.MCI['configuration']
        elif self.ctype == 'DELETE':
            self.resource = self.MCID['changedProperties']['Configuration']['previousValue']
        else:
            self.resource = None

    def get_tag(self, name):
        result = [tag['value'] for tag in self.resource.get('tags', []) if tag['key'] == name]
        if result:
            return result[0]

    def is_vpn_instance(self):
        return self.get_tag('aws:cloudformation:logical-id') == 'VPNServerInstance'

    def is_changed(self, name):
        return self.MCID['changedProperties'].get(name, {}).get('changeType') == 'UPDATE'
