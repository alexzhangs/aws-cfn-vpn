_E='post'
_D='get'
_C=False
_B='data'
_A=None
import os,json,boto3,botocore.vendored.requests as requests
print('Loading function')
def lambda_handler(event,context):
    A='SSM_INSTANCE_LOGICAL_ID';print('Received event: '+json.dumps(event));ec2=Ec2Instance(os.getenv('SSM_STACK_ID'),os.getenv(A))
    if ec2 is _A:raise Exception('{}: not found the EC2 instance'.format(os.getenv(A)))
    print('wait here, the CREATE notification of config may come earlier.');ec2.wait_until_running();print('go on now.');BaseAPI.backend=Backend(host=ec2.public_ip_address or os.getenv('SSM_DOMAIN'),port=os.getenv('SSM_PORT'),user=os.getenv('SSM_ADMIN_USERNAME'),password=os.getenv('SSM_ADMIN_PASSWORD'));action=event['action'].lower();cls=globals()[event['model']]
    if action=='list':return cls.list(**event.get('filter',{}))
    elif action=='save':inst=cls(**event[_B]);return inst.save(method=event.get('method'),fields=event.get('fields'))
    else:raise ValueError('{}: invalid action.'.format(action))
class Ec2Instance:
    def __new__(self,stack_id,logical_id):
        ec2=boto3.resource('ec2');insts=ec2.instances.filter(Filters=[dict(Name='tag:aws:cloudformation:stack-id',Values=[stack_id]),dict(Name='tag:aws:cloudformation:logical-id',Values=[logical_id])])
        for inst in insts:return inst
class Backend:
    def __init__(self,host,port=80,schema='http',user=_A,password=_A):self.url='{schema}://{host}:{port}'.format(host=host,port=port,schema=schema);self.host=host;self.port=port;self.schema=schema;self.user=user;self.password=password;self.session=_A;self.authenticated=_C;self.csrftoken=_A
    def call(self,*args,**kwargs):
        if self.csrftoken and _B in kwargs:kwargs[_B]['csrfmiddlewaretoken']=self.csrftoken;kwargs.update({'headers':{'X-CSRFToken':self.csrftoken}})
        print(args,kwargs);resp=self.session.request(*args,**kwargs)
        if resp:self.csrftoken=self.session.cookies.get('csrftoken',_A)
        print('{}: {}'.format(str(resp),resp.text.replace('\\n','')));return resp
    def authenticate(self,url):
        print('authenticating');self.session=requests.session();resp=self.call(_D,url)
        if resp:
            resp=self.call(_E,url,timeout=5,data=dict(username=self.user,password=self.password,next='/'))
            if resp:self.authenticated=True
        return resp
class BaseAPI:
    path='/';auth_path=_A;backend=_A
    @classmethod
    def get_url(cls,id=_A,auth=_C):url=cls.backend.url+(cls.auth_path if auth else cls.path);return url+'{}/'.format(id)if id else url
    @classmethod
    def call(cls,*args,**kwargs):
        if cls.auth_path and not cls.backend.authenticated:
            if not cls.backend.authenticate(cls.get_url(auth=True)):return
        resp=cls.backend.call(*args,**kwargs)
        if resp is not _A:return resp.json()
class BaseModel:
    class API(BaseAPI):auth_path='/admin/login/'
    def __init__(self,**kwargs):
        A='id'
        for (k,v) in kwargs.items():setattr(self,k,v)
        if not self.__dict__.has_key(A):setattr(self,A,_A)
    @classmethod
    def list(cls,**kwargs):result=cls.API.call(_D,cls.API.get_url(),params=kwargs);return[cls(**item)for item in result or[]]
    def save(self,method=_A,fields=_A):
        if not method:method=_E if self.id is _A else'put'
        result=self.API.call(method,self.API.get_url(self.id),data=self.serialize(fields=fields))
        if result:self.__dict__.update(result)
        return self
    def serialize(self,fields=_A):
        data={}
        for (k,v) in self.__dict__.items():
            if fields and k not in fields:continue
            if isinstance(v,(int,str,unicode)):data[k]=v
        return data
class Domain(BaseModel):
    class API(BaseModel.API):path='/domain/'
class Node(BaseModel):
    class API(BaseModel.API):path='/shadowsocks/node/'
class SSManager(BaseModel):
    class API(BaseModel.API):path='/shadowsocks/ssmanager/'
