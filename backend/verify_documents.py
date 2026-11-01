"""Read-only smoke checks plus non-persistent public fixture uploads; no LLM calls."""
import argparse
import base64
import json
from pathlib import Path
import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--base', required=True)
parser.add_argument('--pdf', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
base = args.base.rstrip('/')
record = {'base': base, 'model_calls': 0, 'checks': []}
with httpx.Client(timeout=60) as client:
    identity = client.post(base + '/api/v1/auth/guest')
    identity.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + identity.json()['token']
    def upload(raw, filename):
        response = client.post(base + '/api/v1/documents/analyze', json={
            'filename': filename, 'content_base64': base64.b64encode(raw).decode(), 'use_model': False})
        response.raise_for_status()
        return response.json()
    result = upload('产品,代码,收益\n公开测试A,001,3%\n公开测试B,002,5%\n'.encode(), 'public-smoke.csv')
    assert result['statistics'][0]['mean'] == 4
    assert result['model_status'] == 'not_requested'
    record['checks'].append({'name': 'csv_values_and_source', 'pass': True, 'source': result['statistics'][0]['min_source']})
    invalid = client.post(base + '/api/v1/documents/analyze', json={'filename': 'x.csv', 'content_base64': '!'})
    assert invalid.status_code == 422
    record['checks'].append({'name': 'invalid_base64', 'pass': True})
    if args.pdf:
        result = upload(args.pdf.read_bytes(), args.pdf.name)
        assert any(e['location'] == '第4页' and '0.60%' in e['text'] for e in result['evidence'])
        record['checks'].append({'name': 'public_fund_pdf_page4_fee', 'pass': True,
                                'evidence_count': len(result['evidence']), 'sha256': result['sha256']})
if args.output:
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=False))
