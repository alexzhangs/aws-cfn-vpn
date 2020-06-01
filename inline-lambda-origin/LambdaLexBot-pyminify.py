_M='PlainText'
_L='content'
_K='contentType'
_J='isValid'
_I='type'
_H='dialogAction'
_G='slots'
_F='name'
_E='VpnInstanceName'
_D='message'
_C='currentIntent'
_B=None
_A='sessionAttributes'
import os,logging,json,boto3
logger=logging.getLogger()
logger.setLevel(logging.DEBUG)
def call_ssm(**C):
    D=boto3.client('lambda');A=D.invoke(FunctionName=os.getenv('LAMBDA_SSM_API_ARN'),Payload=json.dumps(C))
    if A['StatusCode']>=400:raise Exception('Failed to call the Lambda of SSM API. Response: '+A)
    B=json.load(A['Payload'])
    if B.get('errorMessage'):logger.error(B);return _B
    else:return B
def get_slots(intent_request):return intent_request[_C][_G]
def elicit_slot(session_attributes,intent_name,slots,slot_to_elicit,message):return{_A:session_attributes,_H:{_I:'ElicitSlot','intentName':intent_name,_G:slots,'slotToElicit':slot_to_elicit,_D:message}}
def close(session_attributes,fulfillment_state,message):A={_A:session_attributes,_H:{_I:'Close','fulfillmentState':fulfillment_state,_D:message}};return A
def delegate(session_attributes,slots):return{_A:session_attributes,_H:{_I:'Delegate',_G:slots}}
def build_validation_result(is_valid,violated_slot,message_content):
    D='violatedSlot';C=message_content;B=violated_slot;A=is_valid
    if C is _B:return{_J:A,D:B}
    return{_J:A,D:B,_D:{_K:_M,_L:C}}
def get_instances():return call_ssm(action='list',model='Node',filter=_B)
def get_sns_endpoint(instance):
    for A in get_instances()or[]:
        if instance.lower==A.name.lower():return A['sns_endpoint']
def validate_instance(instance):
    A=instance;B=[A.name.lower()for A in get_instances()or[]]
    if A.lower()not in B:return build_validation_result(False,_E,'{}: the instance name you specified does not exist, the valid instance names are: {}.'.format(A,','.join(B)))
    return build_validation_result(True,_B,_B)
def change_ip(intent_request):
    A=intent_request;C=get_slots(A);B=C[_E];F=A['invocationSource']
    if F=='DialogCodeHook':
        if not B:return elicit_slot(A[_A],A[_C][_F],C,_E,_B)
        E=validate_instance(B)
        if not E[_J]:return elicit_slot(A[_A],A[_C][_F],C,_E,E[_D])
    D=get_sns_endpoint(B)
    if not D:return close(A[_A],'Failed',{_K:_M,_L:'{}: not found the SNS endpoint on this instance.'.format(B)})
    G=boto3.resource('sns');H=G.Topic(D);H.publish(TargetArn=D,Message='change_ip');return close(A[_A],'Fulfilled',{_K:_M,_L:'The IP address of instance {} will be replaced with a new one.'.format(B)})
def dispatch(intent_request):
    A=intent_request;logger.debug('dispatch userId={}, intentName={}'.format(A['userId'],A[_C][_F]));B=A[_C][_F]
    if B=='GetNewIpForVpnInstance':return change_ip(A)
    raise Exception('Intent with name '+B+' not supported')
def lambda_handler(event,context):A=event;logger.info('Received event'+json.dumps(A));return dispatch(A)
