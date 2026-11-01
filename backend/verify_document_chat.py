"""Production smoke check with synthetic attachments; no model calls by default."""
import argparse
import base64
import json
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--base',required=True)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
record={'checks':[],'model_calls':0,'private_files_uploaded':False}
with httpx.Client(base_url=args.base.rstrip('/'),timeout=90) as client:
    session=client.post('/api/v1/auth/guest');session.raise_for_status()
    client.headers['Authorization']='Bearer '+session.json()['token']
    documents=[{'filename':'synthetic-products.csv','content_base64':base64.b64encode(b'product,fee\nA,0.5\nB,0.8\n').decode()}]
    first=client.post('/api/v1/documents/chat',json={'question':'Compare fees using the attached CSV','documents':documents})
    first.raise_for_status();result=first.json()
    assert result['model_status']=='not_requested' and 'history_id' not in result
    assert '[D1:R2]' in result['answer'] and result['analyses'][0]['statistics'][0]['max']==0.8
    record['checks'].append('anonymous_cited_document_question')
    second=client.post('/api/v1/documents/chat',json={'question':'What is missing in those values?','documents':documents,
        'history':[{'role':'user','content':result['question']},{'role':'assistant','content':result['answer'][:6000]}]})
    second.raise_for_status()
    assert second.json()['sources'][0]['filename']=='synthetic-products.csv'
    record['checks'].append('followup_with_current_attachments')
    assert client.get('/api/v1/documents/history').status_code==403
    record['checks'].append('anonymous_history_not_accessible')
    assert client.post('/api/v1/auth/logout').status_code==200
record['all_passed']=True
if args.output:args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
