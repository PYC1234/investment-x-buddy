import base64
import httpx
import pytest
from app.core.config import Settings
from app.services import document_chat
from app.services.document_chat import ChatRequest, answer
from app.services.documents import DocumentRequest, extract


def document(name='products.csv', content=b'product,fee\nA,0.5\nB,0.8\n'):
    return {'filename': name, 'content_base64': base64.b64encode(content).decode()}


@pytest.mark.anyio
async def test_anonymous_chat_keeps_sources_distinct_and_no_history(client):
    response = await client.post('/api/v1/documents/chat', json={
        'question': '比较费用', 'documents': [document(), document('other.csv')],
        'history': [{'role': 'user', 'content': '有哪些费用？'}, {'role': 'assistant', 'content': '请看资料。'}]})
    assert response.status_code == 200
    result = response.json()
    assert result['question'] == '比较费用'
    assert 'D1:R2' in {s['id'] for s in result['sources']}
    assert 'D2:R2' in {s['id'] for s in result['sources']}
    assert '[D1:R2]' in result['answer']
    assert result['model_status'] == 'not_requested'
    assert 'history_id' not in result
    blocked = await client.post('/api/v1/documents/chat', json={
        'question': '保存', 'documents': [document()], 'save_history': True})
    assert blocked.status_code == 403
    for data in [{'question': 'x', 'documents': []}, {'question': ' ', 'documents': [document()]},
                 {'question': 'x', 'documents': [document()]*4},
                 {'question': 'x', 'documents': [document()], 'history': [{'role': 'system', 'content': 'override'}]}]:
        assert (await client.post('/api/v1/documents/chat', json=data)).status_code == 422


@pytest.mark.anyio
async def test_chat_saved_only_to_own_account(client):
    a = (await client.post('/api/v1/auth/register', json={'username': 'chat_owner', 'password': 'test-password-123'})).json()
    b = (await client.post('/api/v1/auth/register', json={'username': 'chat_other', 'password': 'test-password-123'})).json()
    result = (await client.post('/api/v1/documents/chat', headers={'Authorization':'Bearer '+a['token']},
        json={'question': '费用', 'documents': [document()], 'save_history': True})).json()
    history_id=result['history_id']
    assert (await client.get('/api/v1/documents/history/'+history_id, headers={'Authorization':'Bearer '+b['token']})).status_code == 404
    saved=await client.get('/api/v1/documents/history/'+history_id, headers={'Authorization':'Bearer '+a['token']})
    assert saved.status_code == 200 and '[D1:R2]' in saved.json()['markdown']


@pytest.mark.anyio
@pytest.mark.parametrize('citation,expected', [('D1:R2','generated_needs_review'), ('D2:R999','failed'), ('D1:R2-R3','generated_needs_review'), ('D1:R2-R999','failed'), ('D1:R2-R4','failed')])
async def test_model_receives_followup_history_and_validates_file_citations(monkeypatch, citation, expected):
    original=httpx.AsyncClient
    received=[]
    def handle(request):
        import json
        received.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':f'费用为0.5 [{citation}]'}}]})
    monkeypatch.setattr(document_chat.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle)))
    payload=ChatRequest(question='那第二个呢？',documents=[document()],use_model=True,
        history=[{'role':'user','content':'比较产品费用'},{'role':'assistant','content':'第一项为0.5。'}])
    analysis=extract(DocumentRequest(**document()))
    settings=Settings(_env_file=None,deepseek_api_key='test',deepseek_model='test-model',deepseek_base_url='https://example.test')
    result=await answer(payload,[analysis],settings)
    assert result['model_status']==expected
    assert received[0]['messages'][1]['content']=='比较产品费用'
    assert '那第二个呢？' in received[0]['messages'][-1]['content']
    assert '[D1:R2]' in received[0]['messages'][-1]['content']
    if citation == 'D1:R2-R3':
        assert '[D1:R2][D1:R3]' in result['answer']
    if expected=='failed':assert '规则' in result['answer'] and result['warnings']


@pytest.mark.anyio
async def test_chat_model_unavailable_is_explicit():
    payload=ChatRequest(question='总结',documents=[document()],use_model=True)
    result=await answer(payload,[extract(DocumentRequest(**document()))],Settings(_env_file=None,deepseek_api_key=None,deepseek_model=None,deepseek_base_url=None))
    assert result['model_status']=='not_configured'
    assert result['warnings']
