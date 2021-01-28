#!/usr/bin/env python

'''
Provide the Lambda interface for the shadowsocks-manager REST APIs:
NameServer, Domain, Record, Node and SSManager.

Example:

import boto3
client = boto3.client('lambda')
response = client.invoke(
    FunctionName='<ARN-of-the-Lambda>', # REQUIRED
    Payload=json.dumps(
        action='list|save|delete',      # REQUIRED
        model='<MODEL>',                # REQUIRED, Values: NameServer,Domain,Record,Node,SSManager
        data={<name>=<value>, ...},     # REQUIRED for action `save`
        method='post|put|patch',        # OPTIONAL for action `save`
        fields=[<name>, ...],           # OPTIONAL for action `save`
        filter={<name>=<value>, ...}    # OPTIONAL for action `list`
    )
)
obj = response['Payload']

'''

import os, json
import boto3, botocore.vendored.requests as requests

print('Loading function')

def lambda_handler(event, context):
    print('Received event: ' + json.dumps(event))
    ec2 = Ec2Instance(os.getenv('SSM_STACK_ID'),
        os.getenv('SSM_INSTANCE_LOGICAL_ID'))

    if ec2 is None:
        raise Exception('{}: not found the EC2 instance'.format(os.getenv('SSM_INSTANCE_LOGICAL_ID')))

    print('wait here, the CREATE notification of config may come earlier.')
    ec2.wait_until_running()
    print('go on now.')

    BaseAPI.backend = Backend(
        host=ec2.public_ip_address or os.getenv('SSM_DOMAIN'),
        port=os.getenv('SSM_PORT'),
        user=os.getenv('SSM_ADMIN_USERNAME'),
        password=os.getenv('SSM_ADMIN_PASSWORD')
    )
    action = event['action'].lower()
    cls = globals()[event['model']]

    if action == 'list':
        insts = cls.list(**(event.get('filter', {}) or {}))
        return [i.serialize() for i in insts]
    elif action == 'save':
        inst = cls(**event['data'])
        inst.save(method=event.get('method'), fields=event.get('fields'))
        return inst.serialize()
    elif action == 'delete':
        inst = cls(**event['data'])
        inst.delete()
        return inst.serialize()
    else:
        raise ValueError('{}: invalid action.'.format(action))

class Ec2Instance(object):
    def __new__(self, stack_id, logical_id):
        ec2 = boto3.resource('ec2')
        insts = ec2.instances.filter(Filters=[
            dict(Name='tag:aws:cloudformation:stack-id', Values=[stack_id]),
            dict(Name='tag:aws:cloudformation:logical-id', Values=[logical_id])])
        for inst in insts: return inst

class Backend(object):
    def __init__(self, host, port=80, schema='http', user=None, password=None):
        self.url = '{schema}://{host}:{port}'.format(host=host, port=port, schema=schema)
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
        resp = self.session.request(*args, **kwargs)
        if resp:
            self.csrftoken = self.session.cookies.get('csrftoken', None)
        print('{}: {}'.format(str(resp), resp.text))
        return resp

    def authenticate(self, url):
        print('authenticating')
        self.session = requests.session()
        resp = self.call('get', url)
        if resp:
            resp = self.call('post', url, timeout=5,
                data=dict(username=self.user, password=self.password, next='/'))
            if resp: self.authenticated = True
        return resp

class BaseAPI(object):
    path = '/'
    auth_path = None
    backend = None

    @classmethod
    def get_url(cls, id=None, auth=False):
        url = cls.backend.url + (cls.auth_path if auth else cls.path)
        return url + '{}/'.format(id) if id else url

    @classmethod
    def call(cls, *args, **kwargs):
        if cls.auth_path and not cls.backend.authenticated:
            if not cls.backend.authenticate(cls.get_url(auth=True)):
                print('failed to authenticate')
                return
        resp = cls.backend.call(*args, **kwargs)
        if resp is not None:
            return resp.json()

class BaseModel(object):
    class API(BaseAPI):
        auth_path = '/admin/login/'

    def __init__(self, **kwargs):
        for k, v in kwargs.items(): setattr(self, k, v)
        if not 'id' in self.__dict__: setattr(self, 'id', None)

    @classmethod
    def list(cls, **kwargs):
        result = cls.API.call('get', cls.API.get_url(), params=kwargs)
        return [cls(**item) for item in result or []]

    def save(self, method=None, fields=None):
        if not method:
            method = 'post' if self.id is None else 'put'
        result = self.API.call(method, self.API.get_url(self.id),
            data=self.serialize(fields=fields))
        if result: self.__dict__.update(result)
        return self

    def delete(self):
        result = self.API.call('delete', self.API.get_url(self.id))
        if result: self.__dict__.update(result)
        return self

    def serialize(self, fields=None):
        data = {}
        for k, v in self.__dict__.items():
            if fields and k not in fields: continue
            if isinstance(v, (int, str)): data[k] = v
        return data

class NameServer(BaseModel):
    class API(BaseModel.API):
        path = '/domain/nameserver/'

class Domain(BaseModel):
    class API(BaseModel.API):
        path = '/domain/domain/'

class Record(BaseModel):
    class API(BaseModel.API):
        path = '/domain/record/'

class Node(BaseModel):
    class API(BaseModel.API):
        path = '/shadowsocks/node/'

class SSManager(BaseModel):
    class API(BaseModel.API):
        path = '/shadowsocks/ssmanager/'
