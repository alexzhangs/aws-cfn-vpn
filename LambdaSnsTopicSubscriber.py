#!/usr/bin/env python

# Description:
#   Receive AWS Config events through SNS, update NameServer, Domain, Record, Node, and SSManager
#   in shadowsocks-manager.

import time, os, json
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
    subject = event['Records'][0]['Sns']['Subject']
    print('SNS subject: ' + subject)
    message = event['Records'][0]['Sns']['Message']
    print('SNS message: ' + message)

    try:
        cicn_inst = CICN(json.loads(message))
    except ValueError as e:
        print('skip this event: ' + str(e))
        return

    cicn_inst.process()

def get_long_region_name(region):
    # get the long name of AWS region
    client = boto3.client('ssm')
    resp = client.get_parameter(Name='/aws/service/global-infrastructure/regions/{region}/longName'.format(region=region))
    return resp['Parameter']['Value']

def get_host_from_domain(domain):
    items = domain.split('.')
    bound = len(items) - 2
    return '.'.join(items[:bound])

def get_root_from_domain(domain):
    items = domain.split('.')
    bound = len(items) - 2
    return '.'.join(items[bound:])

# timeout and delay: in Seconds
def wait_call(timeout, delay, func, *args, **kwargs):
    starter = time.time()
    while (time.time() - starter) < timeout:
        ret = func(*args, **kwargs)
        if ret is not None:
            return ret
        else:
            time.sleep(delay)

def create_record(domain, append=False, **kwargs):
    root = get_root_from_domain(domain)
    host = get_host_from_domain(domain)
    records = call_ssm(action='list', model='Record', filter=dict(host=host, domain__name=root))
    if records:
        record = records[0]
        if append:
            old_set = set(record['answer'].lower().split(','))
            new_set = set(kwargs.pop('answer').lower().split(','))
            if new_set not in old_set:
                record['answer'] = ','.join(old_set.union(new_set))
        record.update(kwargs)
    else:
        domains = call_ssm(action='list', model='Domain', filter=dict(name=root))
        if domains:
            record = dict(host=host, domain=domains[0]['id'], **kwargs)
        else:
            print('not found the instance of Domain: {} for creating the record: {}'.format(root, host))
            return
    return call_ssm(action='save', model='Record', data=record)

def delete_record(domain):
    root = get_root_from_domain(domain)
    host = get_host_from_domain(domain)
    records = call_ssm(action='list', model='Record', filter=dict(host=host, domain__name=root))
    if records:
        return call_ssm(action='delete', model='Record', data=records[0])

def create_node(name, domain, **kwargs):
    nodes = call_ssm(action='list', model='Node', filter=dict(name=name))
    if nodes:
        node = nodes[0]
        node.update(kwargs)
    else:
        root = get_root_from_domain(domain)
        host = get_host_from_domain(domain)
        records = call_ssm(action='list', model='Record', filter=dict(host=host, domain__name=root))
        if records:
            node = dict(name=name, record=records[0]['id'], **kwargs)
        else:
            print('not found the instance of Record: {} for creating the node: {}'.format(domain, name))
            return
    return call_ssm(action='save', model='Node', data=node)

def delete_node(name):
    nodes = call_ssm(action='list', model='Node', filter=dict(name=name))
    if nodes:
        node = nodes[0]
        node['is_active'] = False
        return call_ssm(action='save', model='Node', method='PATCH', data=node, fields=['is_active'])

def create_ssmanager(node_name, **kwargs):
    ssmanagers = call_ssm(action='list', model='SSManager', filter=dict(node__name=node_name))
    if ssmanagers:
        ssmanager = ssmanagers[0]
        ssmanager.update(kwargs)
    else:
        nodes = call_ssm(action='list', model='Node', filter=dict(name=node_name))
        if nodes:
            ssmanager = dict(node = nodes[0]['id'], **kwargs)
        else:
            print('not found the instance of Node: {} for creating the ssmanager'.format(node_name))
            return
    return call_ssm(action='save', model='SSManager', data=ssmanager)


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
            result.update(self.diff_item['changedProperties'].get('SupplementaryConfiguration.Tags', {}).get('previousValue', {}))
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
            print(handler_cls, result)


class Handler(object):

    resource_type = None

    def __init__(self, cicn):
        if self.resource_type != cicn.resource_type:
            raise RuntimeError('expect resource type: {}, but found: {}'.format(self.resource_type, cicn.resource_type))

        self.cicn = cicn

    def create(self):
        pass

    def update(self):
        pass

    def delete(self):
        pass


class NameServerHandler(Handler):

    resource_type = 'AWS::EC2::Instance'

    @property
    def name(self):
        return self.cicn.tags['DomainNameServer']

    @property
    def user(self):
        return self.cicn.tags['DomainNameServerUsername']

    @property
    def credential(self):
        return self.cicn.tags['DomainNameServerCredential']

    def create(self):
        return self.update()

    def update(self):
        nameserver = dict(user=self.user, credential=self.credential)
        nameservers = call_ssm(action='list', model='NameServer', filter=dict(name=self.name))
        if nameservers:
            nameserver['id'] = nameservers[0]['id']

        return call_ssm(action='save', model='NameServer', method='PATCH', data=nameserver, fields=['user','credential'])


class DomainHandler(Handler):

    resource_type = 'AWS::EC2::Instance'

    @property
    def domain(self):
        return self.cicn.tags['Domain']

    def create(self):
        domain = dict(name=self.domain)
        domains = call_ssm(action='list', model='Domain', filter=dict(name=domain))
        if domains:
            domain['id'] = domains[0]['id']

        nameserver = self.cicn.tags.get('DomainNameServer')
        nameservers = call_ssm(action='list', model='NameServer', filter=dict(name=nameserver))
        if nameservers:
            domain['nameserver'] = nameservers[0]['id']

        return call_ssm(action='save', model='Domain', data=domain)

    def update(self):
        return self.create()


class SsmRecordHandler(Handler):

    resource_type = 'AWS::ElasticLoadBalancing::LoadBalancer'

    @property
    def domain(self):
        return self.cicn.tags['SSMDomain']

    def create(self):
        # wait call here, until to get a successful result, because ELB events may come earlier than EC2 events,
        # and therefore EC2 events are responsible for creating Domain instance which is used to create this record.
        return wait_call(
            180, 3,
            create_record, self.domain, type='CNAME', answer=self.cicn.resource['dnsname'],
            # associate a site here, so the domain will be added to ALLOWED_HOSTS.
            site=1)

    def update(self):
        return self.create()


class L2tpRecordHandler(Handler):

    resource_type = 'AWS::EC2::Instance'

    @property
    def domain(self):
        return self.cicn.tags['L2TPDomain']

    def create(self):
        return create_record(self.domain, type='A', answer=self.cicn.resource['publicIpAddress'])

    def update(self):
        return self.create()


class SsnRecordHandler(Handler):

    resource_type = 'AWS::EC2::Instance'

    @property
    def domain(self):
        return self.cicn.tags['SSDomain']

    def create(self):
        return create_record(self.domain, append=True, type='A', answer=self.cicn.resource['publicIpAddress'])

    def update(self):
        return self.create()


class NodeHandler(Handler):

    resource_type = 'AWS::EC2::Instance'

    @property
    def domain(self):
        return self.cicn.tags['SSDomain']

    @property
    def node_name(self):
        return self.cicn.tags['Name']

    def create(self):
        return create_node(
            self.node_name,
            self.domain,
            public_ip=self.cicn.resource['publicIpAddress'],
            private_ip=self.cicn.resource['privateIpAddress'],
            location=get_long_region_name(self.cicn.item['awsRegion']),
            is_active=(self.cicn.resource['state']['name'] == 'running'),
            sns_endpoint=self.cicn.tags.get('SnsTopicArn'),
            sns_access_key=self.cicn.tags.get('AccessKeyForUserSnsPublisher'),
            sns_secret_key=self.cicn.tags.get('SecretKeyForUserSnsPublisher'))

    def update(self):
        return self.create()


class SSManagerHandler(Handler):

    resource_type = 'AWS::EC2::Instance'

    @property
    def node_name(self):
        return self.cicn.tags['Name']

    @property
    def ssmanager(self):
        return self.cicn.tags['SSManager']

    def create(self):
        ssmanager = json.loads(self.ssmanager)
        return create_ssmanager(self.node_name, **ssmanager)

    def update(self):
        return self.create()
