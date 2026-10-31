import base64
import io
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from app.core.config import Settings
from app.services.documents import extract, summarize, DocumentRequest
import httpx
from app.services import documents


def payload(content: bytes, filename='products.csv', **kwargs):
    return {'filename': filename, 'content_base64': base64.b64encode(content).decode(), **kwargs}


@pytest.mark.anyio
async def test_csv_real_values_and_evidence(client):
    response = await client.post('/api/v1/documents/analyze', json=payload('产品,代码,收益,费用\nA,001,3%,0.2\nB,002,5%,\n'.encode()))
    assert response.status_code == 200
    result = response.json()
    assert result['statistics'][0]['mean'] == 4
    assert result['statistics'][0]['min_source'] == 'R2'
    assert all(s['column'] != '代码' for s in result['statistics'])
    assert result['statistics'][1]['missing'] == 1
    assert result['model_status'] == 'not_requested'
    assert result['sha256']


@pytest.mark.anyio
async def test_bad_inputs_and_units(client):
    for content, filename, status in [(b'a,a\n1,2', 'a.csv', 422), (b'a,b\n1', 'a.csv', 422),
                                      (b'broken', 'a.pdf', 422), (b'text', 'a.exe', 415)]:
        assert (await client.post('/api/v1/documents/analyze', json=payload(content, filename))).status_code == status
    r = await client.post('/api/v1/documents/analyze', json=payload(b'value\n1%\n2\n'))
    assert r.json()['statistics'] == []


@pytest.mark.anyio
async def test_scanned_and_too_large_pdf(client):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    data = io.BytesIO()
    writer.write(data)
    r = await client.post('/api/v1/documents/analyze', json=payload(data.getvalue(), 'scan.pdf'))
    assert r.status_code == 422
    assert 'OCR' in r.json()['error']['message']
    r = await client.post('/api/v1/documents/analyze', json={'filename': 'a.csv', 'content_base64': '!'})
    assert r.status_code == 422
    r = await client.post('/api/v1/documents/analyze', content=b' ' * (4*1024*1024+4097))
    assert r.status_code == 413


@pytest.mark.anyio
async def test_text_pdf_extraction(client):
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=400)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 300 Td (Public fund report: management fee 0.50 percent.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    data = io.BytesIO()
    writer.write(data)
    result = await client.post('/api/v1/documents/analyze', json=payload(data.getvalue(), 'public.pdf'))
    assert result.status_code == 200
    assert result.json()['evidence'][0]['id'] == 'P1-1'
    assert '0.50' in result.json()['evidence'][0]['text']


@pytest.mark.anyio
async def test_model_unavailable_does_not_fake_ai():
    result = extract(DocumentRequest(**payload(b'value\n3\n5\n')))
    await summarize(result, Settings(_env_file=None, deepseek_api_key=None, deepseek_model=None, deepseek_base_url=None))
    assert result['model_status'] == 'not_configured'
    assert result['model_summary'] is None


@pytest.mark.anyio
async def test_extreme_evidence_beyond_preview(client):
    csv = 'value\n' + '\n'.join(str(i) for i in range(40))
    result = (await client.post('/api/v1/documents/analyze', json=payload(csv.encode()))).json()
    assert result['statistics'][0]['max_source'] in {e['id'] for e in result['evidence']}


@pytest.mark.anyio
@pytest.mark.parametrize('reference,expected', [('R2', 'generated_needs_review'), ('R999', 'failed')])
async def test_model_citation_validation(monkeypatch, reference, expected):
    original = httpx.AsyncClient
    def handle(request):
        return httpx.Response(200, json={'choices': [{'message': {'content': f'数值为3 [{reference}]'}}]})
    monkeypatch.setattr(documents.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handle)))
    result = extract(DocumentRequest(**payload(b'value\n3\n5\n')))
    settings = Settings(_env_file=None, deepseek_api_key='test-key', deepseek_base_url='https://example.test', deepseek_model='test-model')
    await summarize(result, settings)
    assert result['model_status'] == expected
    assert (result['model_summary'] is not None) == (expected == 'generated_needs_review')
