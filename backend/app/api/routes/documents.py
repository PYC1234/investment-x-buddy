import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from app.core.config import Settings, get_settings
from app.services.documents import DocumentRequest, extract, summarize
from app.services.document_chat import ChatRequest, answer
from app.api.routes.auth import principal, auth_store, account
import time
from uuid import uuid4

router = APIRouter(tags=['document-analysis'])


@router.post('/documents/chat')
async def chat_documents(request: Request, settings: Settings = Depends(get_settings), user=Depends(principal), store=Depends(auth_store)):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 12 * 1024 * 1024 + 100000:
            raise HTTPException(413, '一次最多3份资料，每份不超过3MB')
    try:
        payload = ChatRequest.model_validate(json.loads(body))
        if not payload.question.strip():
            raise ValueError('empty question')
    except (ValueError, ValidationError):
        raise HTTPException(422, '请填写问题并附上1–3份CSV或PDF资料')
    if payload.save_history and user['kind'] != 'account':
        raise HTTPException(403, '登录后才能保存历史；匿名仍可直接问答')
    # Attachments and conversation are supplied for this turn only, never fetched
    # from another user's history or automatically sent to the research tools.
    analyses = []
    for document in payload.documents:
        document.question = payload.question
        analyses.append(await run_in_threadpool(extract, document))
    result = await answer(payload, analyses, settings)
    if payload.save_history:
        history_id = str(uuid4())
        result['filename'] = '对话资料｜' + payload.question[:65]
        result['markdown'] = f"# {payload.question}\n\n{result['answer']}\n\n## 原文来源\n" + '\n'.join(f"- [{s['id']}] {s['filename']} · {s['location']}：{s['text']}" for s in result['sources'])
        with store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT COUNT(*) FROM document_history WHERE owner_id=?', (user['id'],)).fetchone()[0] >= 50:
                raise HTTPException(409, '历史已达50份，请先删除不需要的记录')
            con.execute('INSERT INTO document_history VALUES(?,?,?,?,?)', (history_id, user['id'], result['filename'], json.dumps(result, ensure_ascii=False), time.time()))
        result['history_id'] = history_id
    return result


@router.post('/documents/analyze')
async def analyze_document(request: Request, settings: Settings = Depends(get_settings), user=Depends(principal), store=Depends(auth_store)):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4 * 1024 * 1024 + 4096:
            raise HTTPException(413, '请求过大，请选择不超过3MB的文件')
    try:
        payload = DocumentRequest.model_validate(json.loads(body))
    except (ValueError, ValidationError):
        raise HTTPException(422, '请求格式错误')
    if payload.save_history and user['kind'] != 'account':
        raise HTTPException(403, '登录后才能保存历史')
    result = await run_in_threadpool(extract, payload)
    if payload.use_model:
        before = len(result['warnings'])
        await summarize(result, settings)
        result['markdown'] += ''.join('\n- ' + item for item in result['warnings'][before:])
    if payload.save_history:
        history_id = str(uuid4())
        with store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT COUNT(*) FROM document_history WHERE owner_id=?', (user['id'],)).fetchone()[0] >= 50:
                raise HTTPException(409, '历史已达50份，请先删除不需要的记录')
            con.execute('INSERT INTO document_history VALUES(?,?,?,?,?)', (history_id, user['id'], result['filename'], json.dumps(result, ensure_ascii=False), time.time()))
        result['history_id'] = history_id
    return result


@router.get('/documents/history')
def history(user=Depends(account), store=Depends(auth_store)):
    return store.fetch_all('SELECT id,filename,created FROM document_history WHERE owner_id=? ORDER BY created DESC', (user['id'],))


@router.get('/documents/history/{history_id}')
def history_item(history_id: str, user=Depends(account), store=Depends(auth_store)):
    row = store.fetch_one('SELECT result FROM document_history WHERE id=? AND owner_id=?', (history_id,user['id']))
    if not row:
        raise HTTPException(404, '记录不存在或无访问权限')
    return json.loads(row['result'])


@router.delete('/documents/history/{history_id}')
def delete_history(history_id: str, user=Depends(account), store=Depends(auth_store)):
    with store.connection() as con:
        deleted = con.execute('DELETE FROM document_history WHERE id=? AND owner_id=?', (history_id,user['id'])).rowcount
    if not deleted:
        raise HTTPException(404, '记录不存在或无访问权限')
    return {'ok': True}
