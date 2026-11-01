import base64
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.services.runs import get_run_service
from test_run_flow import build_service

@pytest.mark.anyio
async def test_two_accounts_cannot_read_mutate_or_reuse_each_others_data(tmp_path):
    settings, service = build_service(tmp_path/'isolation.db')
    app=create_app(settings)
    app.dependency_overrides[get_run_service]=lambda:service
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        async def register(name):
            r=await client.post('/api/v1/auth/register',json={'username':name,'password':'Unique test password 123'})
            assert r.status_code==201
            return {'Authorization':'Bearer '+r.json()['token']}
        a,b=await register('account_a'),await register('account_b')
        assert (await client.get('/api/v1/threads')).status_code==401
        await client.put('/api/v1/auth/preferences',headers=a,json={'horizon':'3年','risk':'保守','evidence':True})
        assert (await client.get('/api/v1/auth/preferences',headers=b)).json()=={}
        r=await client.post('/api/v1/runs',headers=a,json={'goal':'Analyze Moutai valuation'})
        assert r.status_code==201
        run=r.json();rid=run['id'];tid=run['thread_id']
        assert service.get_memory(tid)['research_preferences']['risk']=='保守'
        assert (await client.get('/api/v1/threads',headers=b)).json()==[]
        assert len((await client.get('/api/v1/threads',headers=a)).json())==1
        for suffix in ('','/events','/report','/evidence','/tasks','/checkpoints','/tool-calls','/memory'):
            assert (await client.get('/api/v1/runs/'+rid+suffix,headers=b)).status_code==404
        for action,body in [('approve',{'plan_version':1,'allowed_tools':['x']}),('resume',{}),('cancel',{}),('reject',{'plan_version':1,'reason':'x'}),('retry-failed',{'plan_version':1,'expected_updated_at':'x'})]:
            assert (await client.post('/api/v1/runs/'+rid+'/'+action,headers=b,json=body)).status_code==404
        assert (await client.post('/api/v1/runs',headers=b,json={'goal':'Analyze other research','thread_id':tid})).status_code==404
        assert (await client.delete('/api/v1/threads/'+tid,headers=b)).status_code==404
        content=base64.b64encode(b'value\n3\n5\n').decode()
        result=await client.post('/api/v1/documents/analyze',headers=a,json={'filename':'a.csv','content_base64':content,'save_history':True})
        assert result.status_code==200
        hid=result.json()['history_id']
        assert len((await client.get('/api/v1/documents/history',headers=a)).json())==1
        assert (await client.get('/api/v1/documents/history',headers=b)).json()==[]
        for method in (client.get,client.delete):
            assert (await method('/api/v1/documents/history/'+hid,headers=b)).status_code==404
        assert (await client.delete('/api/v1/documents/history/'+hid,headers=a)).status_code==200
        assert (await client.get('/api/v1/documents/history/'+hid,headers=a)).status_code==404
        assert (await client.delete('/api/v1/auth/preferences',headers=a)).status_code==200
        assert service.get_memory(tid)=={}
        assert (await client.delete('/api/v1/threads/'+tid,headers=a)).status_code==200
        assert (await client.get('/api/v1/runs/'+rid,headers=a)).status_code==404
        assert (await client.post('/api/v1/auth/logout',headers=a)).status_code==200
        assert (await client.get('/api/v1/auth/me',headers=a)).status_code==401
        login=await client.post('/api/v1/auth/login',json={'username':'account_a','password':'Unique test password 123'})
        assert login.status_code==200
        assert login.json()['token']!=a['Authorization'][7:]
        row=service.store.fetch_one('SELECT password_hash FROM users WHERE username=?',('account_a',))
        assert 'Unique' not in row['password_hash']

@pytest.mark.anyio
async def test_guests_and_legacy_rows_are_private(tmp_path):
    settings, service=build_service(tmp_path/'legacy.db')
    old=await service.create_run(__import__('app.schemas.research',fromlist=['CreateRunRequest']).CreateRunRequest(goal='Analyze Moutai valuation'))
    app=create_app(settings);app.dependency_overrides[get_run_service]=lambda:service
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        a=(await client.post('/api/v1/auth/guest')).json();b=(await client.post('/api/v1/auth/guest')).json()
        ah={'Authorization':'Bearer '+a['token']};bh={'Authorization':'Bearer '+b['token']}
        assert (await client.get('/api/v1/runs/'+old['id'],headers=ah)).status_code==404
        r=(await client.post('/api/v1/runs',headers=ah,json={'goal':'Analyze Moutai valuation'})).json()
        assert (await client.get('/api/v1/runs/'+r['id'],headers=bh)).status_code==404
        assert (await client.get('/api/v1/runs/'+r['id'],headers=ah)).status_code==200
        assert (await client.get('/api/v1/documents/history',headers=ah)).status_code==403
        assert (await client.post('/api/v1/documents/analyze',headers=ah,json={'filename':'a.csv','content_base64':base64.b64encode(b'x\n1\n').decode(),'save_history':True})).status_code==403
        from app.api.routes.auth import digest
        service.store.execute('UPDATE sessions SET expires=0 WHERE token_hash=?',(digest(a['token']),))
        assert (await client.get('/api/v1/auth/me',headers=ah)).status_code==401
        assert (await client.get('/api/v1/auth/me',headers={'Authorization':'Bearer invalid'})).status_code==401
