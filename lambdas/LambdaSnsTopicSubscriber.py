#!/usr/bin/env python

"""
Receive AWS Config events through SNS, update NameServer, Domain, Record, Node, and SSManager
in shadowsocks-manager.
"""

import json
import os
import botocore, boto3
from abc import ABC, abstractmethod

print('Loading function')

def call_ssm(**kwargs):
    config = botocore.config.Config(read_timeout=15, connect_timeout=5, retries={'max_attempts': 2})
    client = boto3.client('lambda', config=config)
    print('Calling the Lambda of SSM API with: {}'.format(kwargs))
    resp = client.invoke(
        FunctionName=os.getenv('LAMBDA_SSM_API_ARN'),
        Payload=json.dumps(kwargs)
    )
    print('Response: {}'.format(resp))
    if resp['StatusCode'] >= 400:
        raise Exception('Failed to invoke the Lambda of SSM API. Response: {}'.format(resp))

    func_resp = json.load(resp['Payload'])
    print('Response from the SSM API: {}'.format(func_resp))
    if func_resp['status_code'] >= 400:
        raise Exception('Failed to call the SSM API. Response: {}'.format(func_resp))

    return func_resp['body']


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
    # the path of the API
    api_path = None
    # limit the resource type to the specific type for the handler
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
    api_path = '/domain/nameserver/'

    @property
    @abstractmethod
    def name(self):
        pass

    @property
    @abstractmethod
    def env(self):
        pass

    def create(self):
        data = dict(name=self.name, env=self.env)
        nameservers = call_ssm(resource=self.api_path, method='get', params=dict(name=self.name))
        if nameservers:
            return call_ssm(resource='{}{}/'.format(self.api_path, nameservers[0]['id']), method='put', json=data)
        else:
            return call_ssm(resource=self.api_path, method='post', json=data)


class NameServerHandler(NSHandler):
    @property
    def name(self):
        return 'nameserver'

    @property
    def env(self):
        return self.cicn.tags['DomainNameServerEnv']


class SsmNameServerHandler(NSHandler):
    @property
    def name(self):
        return 'ssm-nameserver'
    
    @property
    def env(self):
        return self.cicn.tags['SSMDomainNameServerEnv']
    

class SsnNameServerHandler(NSHandler):
    @property
    def name(self):
        return 'ss-nameserver'
    
    @property
    def env(self):
        return self.cicn.tags['SSDomainNameServerEnv']
    

class L2tpNameServerHandler(NSHandler):
    @property
    def name(self):
        return 'l2tp-nameserver'
    
    @property
    def env(self):
        return self.cicn.tags['L2TPDomainNameServerEnv']


class DomainHandler(Handler):
    api_path = '/domain/domain/'
    # the name of the nameserver that the domain will be associated with, try them in order
    nameserver_try_list = ['nameserver']

    @property
    @abstractmethod
    def name(self):
        pass

    def create(self):
        data = dict(name=self.name)

        for ns_name in self.nameserver_try_list:
            nameservers = call_ssm(resource=NSHandler.api_path, method='get', params=dict(name=ns_name))
            if nameservers:
                data['nameserver'] = nameservers[0]['id']
                break

        domains = call_ssm(resource=self.api_path, method='get', params=dict(name=self.name))
        if domains:
            return call_ssm(resource='{}{}/'.format(self.api_path, domains[0]['id']), method='put', json=data)
        else:
            return call_ssm(resource=self.api_path, method='post', json=data)


class SsmDomainHandler(DomainHandler):
    nameserver_try_list = ['ssm-nameserver', 'nameserver']

    @property
    def name(self):
        return self.cicn.tags['SSMDomain']


class SsnDomainHandler(DomainHandler):
    nameserver_try_list = ['ss-nameserver', 'nameserver']

    @property
    def name(self):
        return self.cicn.tags['SSDomain']


class L2tpDomainHandler(DomainHandler):
    nameserver_try_list = ['l2tp-nameserver', 'nameserver']

    @property
    def name(self):
        return self.cicn.tags['L2TPDomain']


class RecordHandler(Handler):
    api_path = '/domain/record/'
    # record type
    type = 'A'
    # append the answer to the existing record
    append = False
    # associate the record with a Django Site ID
    site = None

    @property
    @abstractmethod
    def fqdn(self):
        pass

    @property
    def answer(self):
        return self.cicn.resource['publicIpAddress']

    def create(self):
        data = dict(
            fqdn=self.fqdn,
            host=None,
            domain=None,
            type=self.type,
            answer=self.answer,
            site=self.site,
        )

        records = call_ssm(resource=self.api_path, method='get', params=dict(fqdn=self.fqdn, type=self.type))
        if records:
            record = records[0]
            if self.append:
                old_set = set(record['answer'].lower().split(','))
                new_set = set(data['answer'].lower().split(','))
                if old_set not in new_set:
                    data['answer'] = ','.join(new_set.union(old_set))
            return call_ssm(resource='{}{}/'.format(self.api_path, record['id']), method='put', json=data)
        else:
            return call_ssm(resource=self.api_path, method='post', json=data)


    def update(self):
        return self.create()

    def delete(self):
        records = call_ssm(resource=self.api_path, method='get', params=dict(fqdn=self.fqdn, type=self.type, answer=self.answer))
        if records:
            return call_ssm(resource='{}{}/'.format(self.api_path, records[0]['id']), method='delete')


class SsmRecordHandler(RecordHandler):
    # associate a site id here, so the domain will be added to ALLOWED_HOSTS.
    # make sure the site id is the same as the Django settings.SITE_ID.
    site = 1

    @property
    def fqdn(self):
        return self.cicn.tags['SSMDomain']


class SsnRecordHandler(RecordHandler):
    # node cluster shares the same domain, so append the answer to the existing record
    append = True

    @property
    def fqdn(self):
        return self.cicn.tags['SSDomain']


class L2tpRecordHandler(RecordHandler):
    @property
    def fqdn(self):
        return self.cicn.tags['L2TPDomain']


class NodeHandler(Handler):
    api_path = '/shadowsocks/node/'

    @property
    def record(self):
        return self.cicn.tags['SSDomain']

    @property
    def name(self):
        return self.cicn.tags['Name']

    def create(self):
        data = dict(
            name=self.name,
            public_ip=self.cicn.resource['publicIpAddress'],
            private_ip=self.cicn.resource['privateIpAddress'],
            location=get_long_region_name(self.cicn.item['awsRegion']),
            is_active=(self.cicn.resource['state']['name'] == 'running'),
            sns_endpoint=self.cicn.tags.get('SnsTopicArn'),
            sns_access_key=self.cicn.tags.get('AccessKeyForUserSnsPublisher'),
            sns_secret_key=self.cicn.tags.get('SecretKeyForUserSnsPublisher'),
        )

        # lookup existing DNS records which must exist
        records = call_ssm(resource=RecordHandler.api_path, method='get', params=dict(fqdn=self.record, type=RecordHandler.type))
        if records:
            data['record'] = records[0]['id']
        else:
            print('not found the instance of Record: {} for creating the node: {}'.format(self.record, self.name))
            return

        # lookup existing nodes with the same name
        nodes = call_ssm(resource=self.api_path, method='get', params=dict(name=self.name))
        if nodes:
            return call_ssm(resource='{}{}/'.format(self.api_path, nodes[0]['id']), method='put', json=data)
        else:
            return call_ssm(resource=self.api_path, method='post', json=data)

    def update(self):
        return self.create()

    def delete(self):
        nodes = call_ssm(resource=self.api_path, method='get', params=dict(name=self.name))
        if nodes:
            node = nodes[0]
            node['is_active'] = False
            return call_ssm(resource='{}{}/'.format(self.api_path, node['id']), method='put', json=node)


class SSManagerHandler(Handler):
    api_path = '/shadowsocks/ssmanager/'

    @property
    def node_name(self):
        return self.cicn.tags['Name']

    @property
    def ssmanager(self):
        return self.cicn.tags['SSManager']

    def create(self):
        data = json.loads(self.ssmanager)

        ssmanagers = call_ssm(resource=self.api_path, method='get', params=dict(node__name=self.node_name))
        if ssmanagers:
            return call_ssm(resource='{}{}/'.format(self.api_path, ssmanagers[0]['id']), method='put', json=data)
        else:
            nodes = call_ssm(resource=NodeHandler.api_path, params=dict(name=self.node_name), method='get')
            if nodes:
                data['node'] = nodes[0]['id']
                return call_ssm(resource=self.api_path, method='post', json=data)
            else:
                print('not found the instance of Node: {} for creating the ssmanager'.format(self.node_name))
                return

    def update(self):
        return self.create()
