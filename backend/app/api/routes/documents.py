import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from app.core.config import Settings, get_settings
from app.services.documents import DocumentRequest, extract, summarize

router = APIRouter(tags=['document-analysis'])


@router.post('/documents/analyze')
async def analyze_document(request: Request, settings: Settings = Depends(get_settings)):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4 * 1024 * 1024 + 4096:
            raise HTTPException(413, '请求过大，请选择不超过3MB的文件')
    try:
        payload = DocumentRequest.model_validate(json.loads(body))
    except (ValueError, ValidationError):
        raise HTTPException(422, '请求格式错误')
    result = await run_in_threadpool(extract, payload)
    if payload.use_model:
        before = len(result['warnings'])
        await summarize(result, settings)
        result['markdown'] += ''.join('\n- ' + item for item in result['warnings'][before:])
    return result
