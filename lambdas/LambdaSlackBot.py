#!/usr/bin/env python

"""
Manage the shadowsocks-manager nodes through a Slack slash command.

Replaces the retired Amazon Lex chatbot integration. Same SNS pipeline
downstream, but invoked from a Slack slash command via an HTTPS POST to
a Lambda Function URL.

Slack slash command grammar (text after `/vpn `):
  change-ip <node-name>   Rotate the EIP on the named node.
  list                    List known node names.
  help                    Show usage.

Security:
  * Every request is authenticated by verifying the X-Slack-Signature
    header against SLACK_SIGNING_SECRET (HMAC-SHA256, constant-time
    compare). Requests older than SLACK_TIMESTAMP_TOLERANCE seconds
    (default 300) are rejected to prevent replay.
  * Optional allowlists (CSV env vars) restrict who can invoke and
    where. If unset, no restriction (allowlist disabled).

Environment variables:
  LAMBDA_SSM_API_ARN        Required. ARN of LambdaSsmApi to look up nodes.
  SLACK_SIGNING_SECRET      Required. From Slack app's "Basic Information".
  SLACK_ALLOWED_USERS       Optional CSV of allowed Slack user IDs (e.g. "U123,U456").
  SLACK_ALLOWED_CHANNELS    Optional CSV of allowed Slack channel IDs.
  SLACK_TIMESTAMP_TOLERANCE Optional integer seconds. Default 300 (5 min).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import parse_qs

import boto3
import botocore

print('Loading function')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_TIMESTAMP_TOLERANCE = 300  # 5 minutes


# ---------- Slack response helpers ----------

def _slack_response(text, response_type='ephemeral'):
    """Build a Lambda-Function-URL response carrying a Slack message body."""
    return {
        'statusCode': 200,
        'headers': {'content-type': 'application/json'},
        'body': json.dumps({'response_type': response_type, 'text': text}),
    }


def _http(status, text):
    """Plain-text HTTP response (used for auth/validation failures)."""
    return {
        'statusCode': status,
        'headers': {'content-type': 'text/plain'},
        'body': text,
    }


# ---------- Slack signature verification ----------

def _verify_signature(event):
    """Return None if request is authentic, else an error response."""
    signing_secret = os.getenv('SLACK_SIGNING_SECRET')
    if not signing_secret:
        logger.error('SLACK_SIGNING_SECRET not set')
        return _http(500, 'server misconfigured')

    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    timestamp = headers.get('x-slack-request-timestamp', '')
    signature = headers.get('x-slack-signature', '')

    try:
        ts_int = int(timestamp)
    except ValueError:
        return _http(401, 'invalid timestamp')

    tolerance = int(os.getenv('SLACK_TIMESTAMP_TOLERANCE', DEFAULT_TIMESTAMP_TOLERANCE))
    if abs(time.time() - ts_int) > tolerance:
        return _http(401, 'stale request')

    body = event.get('body') or ''
    if event.get('isBase64Encoded'):
        body = base64.b64decode(body).decode('utf-8')

    basestring = f'v0:{timestamp}:{body}'.encode('utf-8')
    digest = hmac.new(signing_secret.encode('utf-8'), basestring, hashlib.sha256).hexdigest()
    expected = f'v0={digest}'

    if not hmac.compare_digest(expected, signature):
        logger.warning('signature mismatch')
        return _http(401, 'signature mismatch')

    return None


# ---------- Allowlist ----------

def _check_allowlist(payload):
    """Return None if allowed, else an error Slack response."""
    user = payload.get('user_id', [''])[0]
    channel = payload.get('channel_id', [''])[0]

    allowed_users = [u.strip() for u in os.getenv('SLACK_ALLOWED_USERS', '').split(',') if u.strip()]
    allowed_channels = [c.strip() for c in os.getenv('SLACK_ALLOWED_CHANNELS', '').split(',') if c.strip()]

    if allowed_users and user not in allowed_users:
        logger.info('user %s not in allowlist', user)
        return _slack_response(f':no_entry: User `{user}` is not authorized to use this command.')
    if allowed_channels and channel not in allowed_channels:
        logger.info('channel %s not in allowlist', channel)
        return _slack_response(f':no_entry: This command is not authorized in channel `{channel}`.')
    return None


# ---------- SSM API client (reuses existing LambdaSsmApi) ----------

def _call_ssm(**kwargs):
    config = botocore.config.Config(read_timeout=15, connect_timeout=5, retries={'max_attempts': 2})
    client = boto3.client('lambda', config=config)
    resp = client.invoke(
        FunctionName=os.environ['LAMBDA_SSM_API_ARN'],
        Payload=json.dumps(kwargs),
    )
    if resp['StatusCode'] >= 400:
        raise RuntimeError(f'Lambda invoke failed: {resp}')
    func_resp = json.load(resp['Payload'])
    if func_resp.get('status_code', 500) >= 400:
        raise RuntimeError(f'SSM API call failed: {func_resp}')
    return func_resp['body']


def _get_instances():
    """Return list of dicts with at least {'name', 'sns_endpoint'}."""
    return _call_ssm(resource='/shadowsocks/node/', method='get', params={}) or []


def _get_sns_endpoint(name):
    for i in _get_instances():
        if name.lower() == i['name'].lower():
            return i['sns_endpoint']
    return None


# ---------- Command handlers ----------

HELP_TEXT = (
    '*VPN node control* — usage:\n'
    '`/vpn change-ip <node-name>`  rotate the EIP on a node\n'
    '`/vpn list`                   list known nodes\n'
    '`/vpn help`                   this help'
)


def _cmd_help():
    return _slack_response(HELP_TEXT)


def _cmd_list():
    try:
        names = sorted(i['name'] for i in _get_instances())
    except Exception as e:
        logger.exception('failed to list instances')
        return _slack_response(f':warning: Failed to list nodes: `{e}`')
    if not names:
        return _slack_response(':information_source: No nodes registered.')
    return _slack_response('Known nodes:\n' + '\n'.join(f'• `{n}`' for n in names))


def _cmd_change_ip(args):
    if not args:
        return _slack_response(':warning: Missing node name. Usage: `/vpn change-ip <node-name>`')
    name = args[0]
    try:
        endpoint = _get_sns_endpoint(name)
    except Exception as e:
        logger.exception('lookup failed for %s', name)
        return _slack_response(f':warning: Lookup failed for `{name}`: `{e}`')
    if not endpoint:
        try:
            available = ', '.join(f'`{i["name"]}`' for i in _get_instances())
        except Exception:
            available = '(failed to fetch list)'
        return _slack_response(
            f':warning: Unknown node `{name}`. Available: {available}'
        )
    try:
        boto3.resource('sns').Topic(endpoint).publish(Message='change_ip')
    except Exception as e:
        logger.exception('SNS publish failed')
        return _slack_response(f':warning: Failed to publish to SNS: `{e}`')
    return _slack_response(
        f':rocket: Requested IP rotation for `{name}`. The change will take effect shortly.'
    )


def _dispatch(text):
    parts = (text or '').strip().split()
    if not parts:
        return _cmd_help()
    verb, args = parts[0].lower(), parts[1:]
    if verb in ('help', '-h', '--help', '?'):
        return _cmd_help()
    if verb == 'list':
        return _cmd_list()
    if verb in ('change-ip', 'changeip', 'change_ip'):
        return _cmd_change_ip(args)
    return _slack_response(
        f':warning: Unknown verb `{verb}`. Use `/vpn help` to see options.'
    )


# ---------- Lambda entrypoint ----------

def lambda_handler(event, context):
    # Don't dump the full event — body contains Slack signing material.
    logger.info('request received: path=%s method=%s',
                event.get('rawPath'),
                (event.get('requestContext') or {}).get('http', {}).get('method'))

    # 1. Verify Slack signature (rejects everything else)
    err = _verify_signature(event)
    if err is not None:
        return err

    # 2. Parse Slack-encoded form body
    body = event.get('body') or ''
    if event.get('isBase64Encoded'):
        body = base64.b64decode(body).decode('utf-8')
    payload = parse_qs(body)

    # 3. Allowlist
    err = _check_allowlist(payload)
    if err is not None:
        return err

    # 4. Route on command text
    text = payload.get('text', [''])[0]
    logger.info('cmd from user=%s channel=%s text=%r',
                payload.get('user_id', [''])[0],
                payload.get('channel_id', [''])[0],
                text)
    return _dispatch(text)
