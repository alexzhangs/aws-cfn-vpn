#!/usr/bin/env python

# Description:
#   Receive AWS Config events through SNS, and update Domain, Node and SSManager
#   in shadowsocks-manager.

from __future__ import print_function

import os
import json
import boto3
import botocore.vendored.requests as requests

print('Loading function')

def lambda_handler(event, context):
    print('Received event: ' + json.dumps(event))
    message = event['Records'][0]['Sns']['Message']
    print('Message body: ' + message)

    try:
        ccnm = CCNM(json.loads(message))
    except Exception as e:
        print(str(e))
        return

    if ccnm.requesttype != 'AWS::EC2::Instance':
        print('Skip message request type: ' + ccnm.requesttype)
        return

    if not ccnm.is_vpn_instance():
        print('Skip none VPN instance.')
        return

    ec2 = Ec2Instance(
        os.getenv('SSM_STACK_ID'),
        os.getenv('SSM_INSTANCE_LOGICAL_ID')
    )

    BaseAPI.backend = Backend(
        host=ec2.public_ip_address or os.getenv('SSM_DOMAIN'),
        port=os.getenv('SSM_PORT'),
        user=os.getenv('SSM_ADMIN_USERNAME'),
        password=os.getenv('SSM_ADMIN_PASSWORD')
    )

    node_name = ccnm.get_tag_value(name='Name')
    if node_name:
        node = Node(name=node_name)
        node.public_ip = ccnm.resource['publicIpAddress']
        node.private_ip = ccnm.resource['privateIpAddress']
        node.location = get_long_region_name(ccnm.json['configurationItem']['awsRegion'])
        node.is_active = (ccnm.resource['state']['name'] == 'running')
    else:
        print('There is no tag with name "Name" on the instance. Skip to update Domain, Node and SSManager in shadowsocks-manager.')
        return

    domain_obj_str = ccnm.get_tag_value(name='Domain')
    if domain_obj_str:
        domain = Domain(**json.loads(domain_obj_str))
        domains = Domain.list(name=domain.name)
        if domains:
            domain = domains[0]
        else:
            domain.save()
        node.domain = domain.id
    else:
        print('There is no tag with name "Domain" on the instance. Skip to update Domain in shadowsocks-manager.')
        domain = None

    nodes = Node.list(name=node.name)
    if nodes:
        node.id = nodes[0].id

    if ccnm.changetype == 'CREATE':
        if nodes:
            node.save()
        else:
            node.save()
    elif ccnm.changetype == 'UPDATE':
        if nodes:
            fields = []
            if ccnm.is_property_changed(name='Configuration.PublicIpAddress'):
                fields.append('public_ip')
            if ccnm.is_property_changed(name='Configuration.State.Name'):
                fields.append('is_active')
            if fields:
                node.save(method='patch', fields=fields)
            else:
                print('no need to update node.')
        else:
            node.save()
    elif ccnm.changetype == 'DELETE':
        if nodes:
            node.is_active = False
            node.save(method='patch', fields=['is_active'])
    else:
        print('Skip unsupported change type' + self.changetype)
        return

    ssmanager_obj_str = ccnm.get_tag_value(name='SSManager')
    if ssmanager_obj_str:
        ssmanager = SSManager(**json.loads(ssmanager_obj_str))
        ssmanager.node = node.id
        ssmanagers = SSManager.list(node=node.id)
        if ssmanagers:
            ssmanager = ssmanagers[0]
        else:
            ssmanager.save()
    else:
        print('There is no tag with name "Domain" on the instance. Skip to update SSManager in shadowsocks-manager.')
        ssmanager = None

    return {
        "node": node.serialize(),
        "domain": domain.serialize() if domain else None,
        "ssmanager": ssmanager.serialize() if ssmanager else None
    }

def get_long_region_name(region):
    # get the long name of AWS region
    client = boto3.client('ssm')
    response = client.get_parameter(Name='/aws/service/global-infrastructure/regions/{region}/longName'.format(region=region))
    return response['Parameter']['Value']

class Ec2Instance(object):
    def __new__(self, stack_id, logical_id):
        ec2 = boto3.resource('ec2')
        instances = ec2.instances.filter(Filters=[
            {
                'Name': 'tag:aws:cloudformation:stack-id',
                'Values': [stack_id]
            },
            {
                'Name': 'tag:aws:cloudformation:logical-id',
                'Values': [logical_id]
            }
        ])
        for instance in instances:
            return instance

class CCNM(object):
    # Configuration Item Change Notification Message

    def __init__(self, message):
        if not isinstance(message, dict):
            raise TypeError('{} is not a Dict.'.format(type(message)))

        mtype = message.get('messageType', None)
        if mtype != 'ConfigurationItemChangeNotification':
            raise ValueError('{} is not ConfigurationItemChangeNotification message.'.format(mtype))

        self.changetype = message['configurationItemDiff']['changeType']
        self.requesttype = message['configurationItem']['resourceType']
        if self.changetype in ['CREATE', 'UPDATE']:
            self.resource = message['configurationItem']['configuration']
        elif self.changetype == 'DELETE':
            self.resource = message['configurationItemDiff']['changedProperties']['Configuration']['previousValue']
        else:
            self.resource = None
        self.json = message

    def get_tag_value(self, name):
        result = [tag['value'] for tag in self.resource.get('tags', []) if tag['key'] == name]
        if result:
            return result[0]

    def is_vpn_instance(self):
        return self.get_tag_value('aws:cloudformation:logical-id') == 'VPNServerInstance'

    def is_property_changed(self, name):
        return self.json['configurationItemDiff']['changedProperties'].get(name, {}).get('changeType') == 'UPDATE'

class Backend(object):

    def __init__(self, host, port=80, schema='http', user=None, password=None):
        self.url = '{schema}://{host}:{port}'.format(
            host=host,
            port=port,
            schema=schema
        )
        self.host = host
        self.port = port
        self.schema = schema
        self.user = user
        self.password = password
        self.session = None
        self.authenticated = False
        self.csrftoken = None

    def call(self, *args, **kwargs):
        if self.csrftoken and 'data' in kwargs:
            kwargs['data']['csrfmiddlewaretoken'] = self.csrftoken
            kwargs.update({'headers': {'X-CSRFToken': self.csrftoken}})
        print(args, kwargs)
        response = self.session.request(*args, **kwargs)
        if response:
            self.csrftoken = self.session.cookies.get('csrftoken', None)
        print('{}: {}'.format(str(response), response.text.replace('\n', '')))
        return response

    def authenticate(self, url):
        print('authenticating')
        self.session = requests.session()
        response = self.call('get', url)
        if response:
            response = self.call(
                'post',
                url,
                data={
                    'username': self.user,
                    'password': self.password,
                    'next': '/'
                },
                timeout=5
            )
            if response:
                self.authenticated = True
        return response

class BaseAPI(object):
    path = '/'
    auth_path = None
    backend = None

    @classmethod
    def get_url(cls, id=None, auth=False):
        url = cls.backend.url + (cls.auth_path if auth else cls.path)
        if id:
            return url + '{}/'.format(id)
        else:
            return url

    @classmethod
    def call(cls, *args, **kwargs):
        if cls.auth_path and not cls.backend.authenticated:
            if not cls.backend.authenticate(cls.get_url(auth=True)):
                return

        response = cls.backend.call(*args, **kwargs)
        if response is not None:
            return response.json()

class BaseModel(object):

    class API(BaseAPI):
        auth_path = '/admin/login/'

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not self.__dict__.has_key('id'):
            setattr(self, 'id', None)

    @classmethod
    def list(cls, **kwargs):
        result = cls.API.call('get', cls.API.get_url(), params=kwargs)
        return [cls(**item) for item in result or []]

    def save(self, method=None, fields=None):
        if not method:
            method = 'post' if self.id is None else 'put'
        result = self.API.call(
            method,
            self.API.get_url(self.id),
            data=self.serialize(fields=fields))
        if result:
            self.__dict__.update(result)

    def serialize(self, fields=None):
        data = {}
        for k, v in self.__dict__.items():
            if fields and k not in fields:
                continue
            if isinstance(v, (int, str, unicode)):
                data[k] = v
        return data

class Domain(BaseModel):

    class API(BaseModel.API):
        path = '/domain/'

class Node(BaseModel):

    class API(BaseModel.API):
        path = '/shadowsocks/node/'

class SSManager(BaseModel):

    class API(BaseModel.API):
        path = '/shadowsocks/ssmanager/'
