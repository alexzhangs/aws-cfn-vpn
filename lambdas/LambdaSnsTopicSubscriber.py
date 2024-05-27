#!/usr/bin/env python

"""
Receive AWS Config events through SNS, update NameServer, Domain, Record, Node, and SSManager
in shadowsocks-manager.
"""

import json
import os
import time
import boto3
from abc import ABC, abstractmethod

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
    try:
        subject = event['Records'][0]['Sns']['Subject']
        message = event['Records'][0]['Sns']['Message']
        cicn_inst = CICN(json.loads(message))

        if cicn_inst.change_type == 'DELETE':
            print('skip this event: ' + subject)
            return

        print('Received event: ' + json.dumps(event))
        print('SNS subject: ' + subject)
        print('SNS message: ' + message)
    except ValueError as e:
        print('skip this event: ' + str(e))
        return

    cicn_inst.process()


def get_long_region_name(region):
    # get the long name of AWS region
    client = boto3.client('ssm')
    resp = client.get_parameter(
        Name='/aws/service/global-infrastructure/regions/{region}/longName'.format(region=region))
    return resp['Parameter']['Value']


# timeout and delay: in Seconds
def wait_call(timeout, delay, func, *args, **kwargs):
    starter = time.time()
    while (time.time() - starter) < timeout:
        ret = func(*args, **kwargs)
        if ret is not None:
            return ret
        else:
            time.sleep(delay)


class CICN(object):
    # Configuration Item Change Notification
    type = 'ConfigurationItemChangeNotification'

    def __init__(self, body):
        if not isinstance(body, dict):
            raise ValueError('expect: {} for body, found: {}.'.format(dict, type(body)))

        self.body = body
        if self.type != body.get('messageType'):
            raise ValueError('expect message type: {}, found: {}.'.format(self.type, body.get('messageType')))

        self.diff_item = body['configurationItemDiff']
        self.item = body['configurationItem']
        self.change_type = self.diff_item['changeType']
        self.resource_type = self.item['resourceType']
        self.resource = self._resource

    @property
    def handlers(self):
        cls_name = self.tags.get('ConfigHandlerClass')
        if cls_name:
            return [globals().get(name) for name in cls_name.split(',')]

    @property
    def _resource(self):
        if self.change_type in ['CREATE', 'UPDATE']:
            result = self.item['configuration']
            result.update(self.item.get('supplementaryConfiguration', {}))
            return result
        elif self.change_type == 'DELETE':
            result = self.diff_item['changedProperties']['Configuration']['previousValue']
            result.update(
                self.diff_item['changedProperties'].get('SupplementaryConfiguration.Tags', {}).get('previousValue', {}))
            return result
        else:
            return

    @property
    def tags(self):
        tags = self.resource.get('tags') or self.resource.get('Tags')
        return {item['key']: item['value'] for item in tags or []}

    def is_changed(self, name):
        return self.diff_item['changedProperties'].get(name, {}).get('changeType') == 'UPDATE'

    def process(self):
        for handler_cls in self.handlers or []:
            handler_inst = handler_cls(self)
            result = getattr(handler_inst, self.change_type.lower())()
            print(self.change_type, handler_cls, result)


class Handler(ABC):
    resource_type = 'AWS::EC2::Instance'

    def __init__(self, cicn):
        if self.resource_type != cicn.resource_type:
            raise RuntimeError('expect resource type: {}, but found: {}'.format(self.resource_type, cicn.resource_type))

        self.cicn = cicn

    @abstractmethod
    def create(self):
        pass

    def update(self):
        return self.create()

    def delete(self):
        pass


class NSHandler(Handler):
    @property
    @abstractmethod
    def name(self):
        pass

    @property
    @abstractmethod
    def env(self):
        pass

    def create(self):
        nameserver = dict(name=self.name, env=self.env)
        nameservers = call_ssm(action='list', model='NameServer', filter=dict(name=self.name))
        if nameservers:
            nameserver['id'] = nameservers[0]['id']

        return call_ssm(action='save', model='NameServer', method='PATCH', data=nameserver,
                        fields=['env'])


class NameServerHandler(NSHandler):
    @property
    def name(self):
        return 'nameserver'

    @property
    def env(self):
        return self.cicn.tags['DomainNameServerEnv']


class SsmNameServerHandler(NameServerHandler):
    @property
    def name(self):
        return 'ssm-nameserver'
    
    @property
    def env(self):
        return self.cicn.tags['SSMDomainNameServerEnv']
    

class SsnNameServerHandler(NameServerHandler):
    @property
    def name(self):
        return 'ss-nameserver'
    
    @property
    def env(self):
        return self.cicn.tags['SSDomainNameServerEnv']
    

class L2tpNameServerHandler(NameServerHandler):
    @property
    def name(self):
        return 'l2tp-nameserver'
    
    @property
    def env(self):
        return self.cicn.tags['L2TPDomainNameServerEnv']


class DomainHandler(Handler):
    # the name of the nameserver that the domain will be associated with, try them in order
    nameservers = ['nameserver']

    @property
    @abstractmethod
    def domain(self):
        pass

    def create(self):
        domain = dict(name=self.domain)
        domains = call_ssm(action='list', model='Domain', filter=dict(name=self.domain))
        if domains:
            domain['id'] = domains[0]['id']

        for nameserver in self.nameserver:
            nameservers = call_ssm(action='list', model='NameServer', filter=dict(name=nameserver))
            if nameservers:
                domain['nameserver'] = nameservers[0]['id']
                break

        return call_ssm(action='save', model='Domain', data=domain)


class SsmDomainHandler(DomainHandler):
    nameservers = ['ssm-nameserver', 'nameserver']

    @property
    def domain(self):
        return self.cicn.tags['SSMDomain']


class SsnDomainHandler(DomainHandler):
    nameservers = ['ss-nameserver', 'nameserver']

    @property
    def domain(self):
        return self.cicn.tags['SSDomain']


class L2tpDomainHandler(DomainHandler):
    nameservers = ['l2tp-nameserver', 'nameserver']

    @property
    def domain(self):
        return self.cicn.tags['L2TPDomain']


class RecordHandler(Handler):
    # record type
    type = 'A'
    # append the answer to the existing record
    append = False
    # associate the record with a Django Site ID
    site = None

    @property
    @abstractmethod
    def domain(self):
        pass

    @property
    def answer(self):
        return self.cicn.resource['publicIpAddress']

    def create(self):
        kwargs = dict(
            fqdn=self.domain,
            type=self.type,
            answer=self.answer,
            site=self.site,
        )

        records = call_ssm(action='list', model='Record', filter=dict(fqdn=self.domain))
        if records:
            record = records[0]
            if self.append:
                old_set = set(record['answer'].lower().split(','))
                new_set = set(kwargs.pop('answer').lower().split(','))
                if new_set not in old_set:
                    record['answer'] = ','.join(old_set.union(new_set))
            record.update(kwargs)
        else:
            record = dict(fqdn=self.domain, **kwargs)
        return call_ssm(action='save', model='Record', data=record)

    def update(self):
        return self.create()

    def delete(self):
        records = call_ssm(action='list', model='Record', filter=dict(fqdn=self.domain))
        if records:
            return call_ssm(action='delete', model='Record', data=records[0])


class SsmRecordHandler(RecordHandler):
    # associate a site here, so the domain will be added to ALLOWED_HOSTS.
    site = 1

    @property
    def domain(self):
        return self.cicn.tags['SSMDomain']


class SsnRecordHandler(Handler):
    # node cluster shares the same domain, so append the answer to the existing record
    append = True

    @property
    def domain(self):
        return self.cicn.tags['SSDomain']


class L2tpRecordHandler(Handler):
    @property
    def domain(self):
        return self.cicn.tags['L2TPDomain']


class NodeHandler(Handler):
    @property
    def domain(self):
        return self.cicn.tags['SSDomain']

    @property
    def node_name(self):
        return self.cicn.tags['Name']

    def create(self):
        kwargs = dict(
            public_ip=self.cicn.resource['publicIpAddress'],
            private_ip=self.cicn.resource['privateIpAddress'],
            location=get_long_region_name(self.cicn.item['awsRegion']),
            is_active=(self.cicn.resource['state']['name'] == 'running'),
            sns_endpoint=self.cicn.tags.get('SnsTopicArn'),
            sns_access_key=self.cicn.tags.get('AccessKeyForUserSnsPublisher'),
            sns_secret_key=self.cicn.tags.get('SecretKeyForUserSnsPublisher'),
        )
        
        # lookup existing nodes with the same name
        nodes = call_ssm(action='list', model='Node', filter=dict(name=self.node_name))
        if nodes:
            # use existing node
            node = nodes[0]
            node.update(kwargs)
        else:
            # create new node
            node = dict(name=self.node_name, **kwargs)

        # lookup existing DNS records which must exist
        records = call_ssm(action='list', model='Record', filter=dict(fqdn=self.domain))
        if records:
            node['record'] = records[0]['id']
        else:
            print('not found the instance of Record: {} for creating the node: {}'.format(self.domain, self.node_name))
            return
        return call_ssm(action='save', model='Node', data=node)

    def update(self):
        return self.create()

    def delete(self):
        nodes = call_ssm(action='list', model='Node', filter=dict(name=self.name))
        if nodes:
            node = nodes[0]
            node['is_active'] = False
            return call_ssm(action='save', model='Node', method='PATCH', data=node, fields=['is_active'])


class SSManagerHandler(Handler):
    @property
    def node_name(self):
        return self.cicn.tags['Name']

    @property
    def ssmanager(self):
        return self.cicn.tags['SSManager']

    def create(self):
        kwargs = json.loads(self.ssmanager)

        ssmanagers = call_ssm(action='list', model='SSManager', filter=dict(node__name=self.node_name))
        if ssmanagers:
            ssmanager = ssmanagers[0]
            ssmanager.update(kwargs)
        else:
            nodes = call_ssm(action='list', model='Node', filter=dict(name=self.node_name))
            if nodes:
                ssmanager = dict(node=nodes[0]['id'], **kwargs)
            else:
                print('not found the instance of Node: {} for creating the ssmanager'.format(self.node_name))
                return
        return call_ssm(action='save', model='SSManager', data=ssmanager)

    def update(self):
        return self.create()
