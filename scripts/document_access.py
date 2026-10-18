"""Scoped Asset document access. Secrets are Windows DPAPI-encrypted, never printed.
Provision is explicitly operator-invoked; normal reads/uploads need no admin key.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import time
import urllib.request
import urllib.error
import win32crypt

BASE = 'https://inhwadbibwkakacdvoxu.supabase.co'
REF = 'inhwadbibwkakacdvoxu'
EMAIL = 'hermes-asset-documents@360-llc.com'
ROLE = 'asset_document_operator'
HOME = Path(os.environ['LOCALAPPDATA']) / 'hermes'
CREDENTIAL = HOME / 'assets' / 'document-access.dpapi'

class ApiError(Exception):
    def __init__(self,status):
        self.status=status
        super().__init__(f'API HTTP {status}; response omitted to protect credentials')

def request(url,method='GET',headers=None,payload=None,raw=None):
    data=raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    h=dict(headers or {})
    if payload is not None:h['Content-Type']='application/json'
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=data,method=method,headers=h),timeout=60) as r:
            body=r.read()
            return json.loads(body) if 'json' in r.headers.get('Content-Type','') and body else body
    except urllib.error.HTTPError as e:
        error=ApiError(e.code)
        try:
            detail=json.loads(e.read())
            error.api_code=str(detail.get('error') or detail.get('code') or '')
        except (ValueError,TypeError):error.api_code=''
        raise error from None

def save(data):
    CREDENTIAL.parent.mkdir(parents=True,exist_ok=True)
    encrypted=win32crypt.CryptProtectData(json.dumps(data).encode(),'Asset document operator',None,None,None,0)
    temp=CREDENTIAL.with_suffix('.tmp')
    temp.write_bytes(encrypted)
    os.replace(temp,CREDENTIAL)

def load():
    return json.loads(win32crypt.CryptUnprotectData(CREDENTIAL.read_bytes(),None,None,None,0)[1])

def claims(token):
    part=token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))

def provision():
    if CREDENTIAL.exists():raise RuntimeError('Credential exists; refusing automatic identity reset')
    management=json.loads((HOME/'mcp-tokens/supabase.json').read_text())['access_token']
    keys=request(f'https://api.supabase.com/v1/projects/{REF}/api-keys?reveal=true',headers={'Authorization':'Bearer '+management})
    admin=next(x['api_key'] for x in keys if x.get('type')=='secret' and x.get('name')=='default')
    public=next(x['api_key'] for x in keys if x.get('type')=='publishable' and x.get('name')=='default')
    headers={'apikey':admin}
    users=request(BASE+'/auth/v1/admin/users?page=1&per_page=1000',headers=headers)['users']
    if any(x.get('email','').lower()==EMAIL for x in users):raise RuntimeError('Existing identity; inspect before recovery, do not reset')
    password=secrets.token_urlsafe(48)+'aA9!'
    data={'email':EMAIL,'password':password,'publishable_key':public}
    # Persist recovery material first, encrypted, before creating external identity.
    save(data)
    user=request(BASE+'/auth/v1/admin/users','POST',headers,payload={'email':EMAIL,'password':password,'email_confirm':True,'role':ROLE,'app_metadata':{'managed_by':'hermes-asset-documents'},'user_metadata':{'purpose':'Asset insurance document ingestion'}})
    verified=request(BASE+'/auth/v1/admin/users/'+user['id'],headers=headers)
    assert verified['email']==EMAIL and verified['role']==ROLE
    data['user_id']=user['id'];save(data)
    client=Client(force_password=True)
    print(json.dumps({'identity':EMAIL,'role':ROLE,'provisioned_and_read_back':True,'encrypted_credential':str(CREDENTIAL),'verified_user':client.user['id']}))

from contextlib import contextmanager
import msvcrt

@contextmanager
def credential_lock():
    CREDENTIAL.parent.mkdir(parents=True,exist_ok=True)
    with CREDENTIAL.with_suffix('.lock').open('a+b') as lock:
        lock.seek(0,2)
        if lock.tell()==0:lock.write(b'0');lock.flush()
        deadline=time.monotonic()+20
        while True:
            try:
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:
                if time.monotonic()>=deadline:raise RuntimeError('Document credential in use; retry after current operation') from None
                time.sleep(.1)
        try:yield
        finally:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

class Client:
    def __init__(self,force_refresh=False,force_password=False):
        with credential_lock():self._initialize(force_refresh,force_password)
    def _initialize(self,force_refresh,force_password):
        self.data=load()
        d=self.data
        session=d.get('session',{})
        if force_password or force_refresh or session.get('expires_at',0)<time.time()+120:
            result=None
            if not force_password and session.get('refresh_token'):
                try:result=request(BASE+'/auth/v1/token?grant_type=refresh_token','POST',{'apikey':d['publishable_key']},payload={'refresh_token':session['refresh_token']})
                except ApiError as e:
                    if e.status not in (400,401):raise
            if result is None:
                result=request(BASE+'/auth/v1/token?grant_type=password','POST',{'apikey':d['publishable_key']},payload={'email':d['email'],'password':d['password']})
            assert claims(result['access_token'])['role']==ROLE
            d['session']={k:result[k] for k in ('access_token','refresh_token','expires_at')}
            save(d)
        self.headers={'apikey':d['publishable_key'],'Authorization':'Bearer '+d['session']['access_token']}
        self.user=request(BASE+'/auth/v1/user',headers=self.headers)
        assert self.user['email']==EMAIL and self.user['id']==d['user_id']
        assert claims(d['session']['access_token'])['role']==ROLE
    def call(self,path,method='GET',payload=None,raw=None,extra=None):
        return request(BASE+path,method,{**self.headers,**(extra or {})},payload,raw)
    def assets(self):
        return self.call('/rest/v1/assets?select=id,vin,unit_no,name,entity,status,updated_at&order=id')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['provision','health','refresh-check','password-check','inventory']);p.add_argument('--output');args=p.parse_args()
    if args.action=='provision':provision()
    else:
        c=Client(force_refresh=args.action=='refresh-check',force_password=args.action=='password-check')
        rows=c.assets()
        if args.action=='inventory':
            assert args.output
            Path(args.output).write_text(json.dumps(rows,indent=2),encoding='utf-8')
        print(json.dumps({'action':args.action,'identity_verified':True,'role':ROLE,'assets_read':len(rows),'secrets_printed':False}))
