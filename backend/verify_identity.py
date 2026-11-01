"""Production smoke test with two disposable accounts and synthetic CSV only."""
import base64
import json
import secrets
import argparse
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--base',required=True)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
base=args.base.rstrip('/')+'/api/v1'
checks=[]
with httpx.Client(timeout=60) as client:
    accounts=[]
    for _ in range(2):
        credentials={'username':'verify_'+secrets.token_hex(8),'password':secrets.token_urlsafe(24)}
        r=client.post(base+'/auth/register',json=credentials);r.raise_for_status()
        accounts.append({'Authorization':'Bearer '+r.json()['token']})
    a,b=accounts
    assert client.get(base+'/auth/me').status_code==401
    content=base64.b64encode(b'product,value\npublic-test-A,3\npublic-test-B,5\n').decode()
    r=client.post(base+'/documents/analyze',headers=a,json={'filename':'isolation-smoke.csv','content_base64':content,'save_history':True})
    r.raise_for_status();hid=r.json()['history_id']
    assert client.get(base+'/documents/history',headers=b).json()==[]
    assert client.get(base+'/documents/history/'+hid,headers=b).status_code==404
    assert client.delete(base+'/documents/history/'+hid,headers=b).status_code==404
    assert client.get(base+'/documents/history/'+hid,headers=a).status_code==200
    checks.append('account_history_isolation')
    r=client.put(base+'/auth/preferences',headers=a,json={'risk':'保守','horizon':'3–5 年','evidence':True});r.raise_for_status()
    assert client.get(base+'/auth/preferences',headers=b).json()=={}
    checks.append('account_memory_isolation')
    client.delete(base+'/auth/preferences',headers=a).raise_for_status()
    client.delete(base+'/documents/history/'+hid,headers=a).raise_for_status()
    assert client.get(base+'/documents/history/'+hid,headers=a).status_code==404
    checks.append('owned_data_deletion')
    r=client.post(base+'/auth/logout',headers=a);r.raise_for_status()
    assert client.get(base+'/auth/me',headers=a).status_code==401
    client.post(base+'/auth/logout',headers=b).raise_for_status()
    checks.append('logout_revocation')
record={'checks':checks,'all_passed':True,'private_files_uploaded':False,'model_calls':0,'note':'Two random verification accounts remain; all test history/preferences removed and sessions revoked. Credentials not logged.'}
if args.output:args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
