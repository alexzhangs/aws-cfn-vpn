#!/usr/bin/env python

"""
Provide the Lambda interface for the DRF REST APIs.

Usage Example:

import boto3
client = boto3.client('lambda')
resp = client.invoke(
    FunctionName='<ARN-of-the-Lambda>',         # REQUIRED
    Payload=json.dumps(dict(                    # REQUIRED
        resource=/path/to/resource/',           # REQUIRED
        method='get|post|put|patch|delete',     # REQUIRED
        params=dict(name=value, ...),           # OPTIONAL
        json=dict(name=value, ...),             # OPTIONAL
        data=dict(name=value, ...),             # OPTIONAL
    ))
)
if resp['StatusCode'] == 200:
    if resp['Payload']['status_code'] < 400:
        obj = resp['Payload']['body']
    else:
        print('Error: {}'.format(resp['Payload']['body']))
else:
    print('Error: {}'.format(resp['Payload']))
"""

import os
import json
from urllib.parse import urljoin
# Lambda (since python3.8) does not have the `requests` module, so it needs to be included
#  in the deployment package or the Lambda layer
import requests

print('Loading function')


class DRFAPI:
    """
    A class used to interact with a Django Rest Framework API.
    """

    def __init__(self, scheme='http', host='localhost', username='admin', password='password',
                 login_path='/admin/login/', api_base='/', csrf_enabled=False, timeout=30):
        self.scheme = scheme
        self.host = host
        self.username = username
        self.password = password
        self.login_path = login_path
        self.api_base = api_base
        self.csrf_enabled = csrf_enabled
        self.timeout = timeout

        self.session = requests.Session()
        self.authenticated = False
        self.csrf_token = None

    def get_url(self, resource):
        base_url = '{scheme}://{host}{base}'.format(scheme=self.scheme, host=self.host, base=self.api_base)
        return urljoin(base_url, resource.lstrip('/'))

    def authenticate(self):
        print('Authenticating ...')
        response = self.call(self.login_path, auth=False, method='get')
        response.raise_for_status()
        response = self.call(self.login_path, auth=False, method='post', data={
            'username': self.username,
            'password': self.password,
            'next': '/',
        })
        response.raise_for_status()
        self.authenticated = True

    def call(self, resource, auth=True, **kwargs):
        if not self.authenticated and auth:
            self.authenticate()

        kwargs.setdefault('url', self.get_url(resource))
        kwargs.setdefault('timeout', self.timeout)

        if self.csrf_enabled and self.session.cookies.get('csrftoken'):
            self.session.headers['X-CSRFToken'] = self.session.cookies.get('csrftoken')

        print('Calling API: {}'.format(kwargs))
        response = self.session.request(**kwargs)
        response.raise_for_status()
        return response


def lambda_handler(event, context):
    """
    Handles an AWS Lambda event by making a request to a Django Rest Framework API.

    Parameters
    ----------
    event : dict
        The event data.

        resource : str
            The path to the resource.
        **kwargs : dict
            The keyword arguments to pass to requests.Session.request.

    context : object
        The context object. Not used in this function.

    Returns
    -------
    dict
        A dictionary containing the status code and body of the API response.
        
        status_code : int
            The status code of the API response.
        body : [dict | list | str]
            The body of the API response.
    """

    print('Received event: ' + json.dumps(event))

    api_params = {
        'scheme': os.getenv('SSM_SCHEME'),
        'host': os.getenv('SSM_HOST'),
        'username': os.getenv('SSM_ADMIN_USERNAME'),
        'password': os.getenv('SSM_ADMIN_PASSWORD'),
        'login_path': os.getenv('SSM_LOGIN_PATH'),
        'api_base': os.getenv('SSM_API_BASE'),
        'csrf_enabled': lambda x: x.lower() in ['true', '1'] if os.getenv('SSM_CSRF_ENABLED') else None,
        'timeout': os.getenv('SSM_TIMEOUT'),
    }
    api_params = {k: v for k, v in api_params.items() if v is not None}

    try:
        api = DRFAPI(**api_params)
        response = api.call(**event)
        print('Response: {} {}'.format(response.status_code, response.json()))
    except requests.HTTPError as e:
        print('Error: {}'.format(e))
        return {'status_code': e.response.status_code, 'body': str(e)}
    except Exception as e:
        print('Error: {}'.format(e))
        return {'status_code': 500, 'body': str(e)}

    return {
        'status_code': response.status_code,
        'body': response.json()
    }