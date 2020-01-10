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

class DRF(object):

    class Meta:
        api_baseurl = 'http://' + os.getenv('SSM_DOMAIN') + ':' + os.getenv('SSM_PORT')
        api_loginurl = api_baseurl + '/admin/login/'
        api_admin_username = os.getenv('SSM_ADMIN_USERNAME')
        api_admin_password = os.getenv('SSM_ADMIN_PASSWORD')
        api_path = None

    session = None

    @classmethod
    def authenticate(cls):
        print('authenticating')
        session = requests.session()
        response = session.get(cls.Meta.api_loginurl)
        if response:
            csrftoken = response.cookies['csrftoken']
        else:
            print('{}: failed to get login url: {}'.format(str(response), cls.Meta.api_loginurl))
            return response
        response = session.post(
            cls.Meta.api_loginurl,
            data={
                'username': cls.Meta.api_admin_username,
                'password': cls.Meta.api_admin_password,
                'csrfmiddlewaretoken': csrftoken,
                'next': '/'
            }
        )
        if response:
            cls.session = session
        else:
            print('{}: failed to authenticate: {}'.format(str(response), cls.Meta.api_loginurl))
        return response

    @classmethod
    def get_api_url(cls, id=None):
        url = cls.Meta.api_baseurl + cls.Meta.api_path
        if id:
            return '{}{}/'.format(url, id)
        else:
            return url

    @classmethod
    def call(cls, method, url, params=None, data=None, headers={}):
        if not cls.session:
            if not cls.authenticate():
                return

        csrftoken = cls.session.cookies.get('csrftoken', None)
        if csrftoken and data and method in ['post', 'put', 'patch']:
            data['csrfmiddlewaretoken'] = csrftoken
            headers['X-CSRFToken'] = csrftoken

        print('{} {}\nInput Data: {}'.format(method.upper(), url, data))
        response = getattr(cls.session, method)(
            url,
            params=params,
            data=data,
            headers=headers
        )
        print('{}: {}'.format(str(response), response.text))
        if not response:
            return

        return response.json()

class Base(DRF):

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not self.__dict__.has_key('id'):
            setattr(self, 'id', None)

    @classmethod
    def list(cls, **kwargs):
        result = cls.call('get', cls.get_api_url(), params=kwargs)
        return [cls(**item) for item in result]

    def save(self, method=None, fields=None):
        if not method:
            method = 'post' if self.id is None else 'put'
        url = self.get_api_url(self.id)
        result = self.__class__.call(method, url, data=self.serialize(fields=fields))
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

class Domain(Base):

    class Meta(Base.Meta):
        api_path = '/domain/'

class Node(Base):

    class Meta(Base.Meta):
        api_path = '/shadowsocks/node/'

class SSManager(Base):

    class Meta(Base.Meta):
        api_path = '/shadowsocks/ssmanager/'
