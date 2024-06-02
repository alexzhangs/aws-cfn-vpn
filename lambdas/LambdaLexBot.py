#!/usr/bin/env python

"""
Manage the shadowsocks-manager nodes through AWS Lex Bot.
"""

import botocore, boto3
import json
import logging
import os

print('Loading function')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


# Helpers to build responses which match the structure of the necessary dialog actions

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


def get_slots(intent_request):
    return intent_request['currentIntent']['slots']


def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ElicitSlot',
            'intentName': intent_name,
            'slots': slots,
            'slotToElicit': slot_to_elicit,
            'message': message
        }
    }


def close(session_attributes, fulfillment_state, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': message
        }
    }


def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }


# Helper Functions

def build_validation_result(is_valid, violated_slot, message_content):
    if message_content is None:
        return {
            'isValid': is_valid,
            'violatedSlot': violated_slot,
        }

    return {
        'isValid': is_valid,
        'violatedSlot': violated_slot,
        'message': {'contentType': 'PlainText', 'content': message_content}
    }


def get_instances():
    return call_ssm(resource='/shadowsocks/node/', method='get', params={})


def get_sns_endpoint(instance):
    for i in get_instances() or []:
        if instance.lower() == i['name'].lower():
            return i['sns_endpoint']


def validate_instance(instance):
    names = [i['name'].lower() for i in get_instances() or []]
    if instance.lower() not in names:
        return build_validation_result(
            False,
            'VpnInstanceName',
            '{}: the instance name you specified does not exist, '
            'the valid instance names are: {}.'.format(instance, ','.join(names)))

    return build_validation_result(True, None, None)


# Functions that control the bot's behavior

def change_ip(intent_request):
    # Performs dialog management and fulfillment for changing IP address.

    slots = get_slots(intent_request)
    instance = slots['VpnInstanceName']
    source = intent_request['invocationSource']

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.

        if not instance:
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               'VpnInstanceName',
                               None)

        validation_result = validate_instance(instance)
        if not validation_result['isValid']:
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               'VpnInstanceName',
                               validation_result['message'])

    # Send the SNS message for changing the IP address for the node.
    sns_endpoint = get_sns_endpoint(instance)
    if not sns_endpoint:
        return close(intent_request['sessionAttributes'],
                     'Failed',
                     {'contentType': 'PlainText',
                      'content': '{}: not found the SNS endpoint on this instance.'.format(instance)})
    resource = boto3.resource('sns')
    topic = resource.Topic(sns_endpoint)
    topic.publish(
        Message='change_ip'
    )
    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'The IP address of instance {} will be replaced with a new one.'.format(instance)})


# Intents

def dispatch(intent_request):
    # Called when the user specifies an intent for this bot.

    logger.debug(
        'dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'GetNewIpForVpnInstance':
        return change_ip(intent_request)

    raise Exception('Intent with name ' + intent_name + ' not supported')


# Main handler

def lambda_handler(event, context):
    # Route the incoming request based on intent.
    # The JSON body of the request is provided in the event slot.

    logger.info('Received event' + json.dumps(event))

    return dispatch(event)
