from typing import Any

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.services.annual_evidence import upload_task
from app.services.documents import DocumentRequest, extract
from app.services.research_sources import available_sources
from app.schemas.research import AnnualScope
import asyncio
import time
import json
from app.api.routes.auth import principal, limit

from app.schemas.research import ApprovalRequest, CreateRunRequest, FollowupRequest, RejectRequest, RetryFailedRequest, RevisePlanRequest, SupplementRequest
from app.services.runs import RunService, get_run_service


def access(request: Request, user=Depends(principal), service: RunService = Depends(get_run_service)):
    run_id = request.path_params.get('run_id')
    if run_id and not service.store.fetch_one('SELECT r.id FROM runs r JOIN threads t ON t.id=r.thread_id WHERE r.id=? AND t.owner_id=?', (run_id, user['id'])):
        raise HTTPException(404, '任务不存在或无访问权限')
    return user

router = APIRouter(tags=["research-runs"], dependencies=[Depends(access)])


@router.post("/runs", status_code=201)
async def create_run(request: CreateRunRequest, http_request: Request, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    user = http_request.state.user
    if request.thread_id and not service.store.fetch_one('SELECT id FROM threads WHERE id=? AND owner_id=?', (request.thread_id, user['id'])):
        raise HTTPException(404, '研究线程不存在或无访问权限')
    if user['kind'] == 'account' and not request.preferences:
        request = request.model_copy(update={'preferences': json.loads(user['preferences'])})
    limit(service.store, 'research-create:'+user['id'], service.settings.max_run_requests_per_hour, seconds=3600)
    result = await service.create_run(request, owner_id=user['id'])
    return result


@router.get("/annual-report-availability")
def annual_report_availability(symbol: str, fiscal_year: int, service: RunService = Depends(get_run_service)):
    try:
        scope = AnnualScope(symbol=symbol, fiscal_year=fiscal_year)
    except ValidationError as exc:
        raise HTTPException(422, "请选择有效的 A 股代码和财年。") from exc
    filings = available_sources(service.settings.research_data_dir, scope.symbol).get("search_company_filings", {})
    return {"filing_available": scope.fiscal_year in filings.get("fiscal_years", [])}


class AnnualUpload(DocumentRequest):
    expected_updated_at: str = Field(min_length=1, max_length=100)
    plan_version: int = Field(ge=1)
    confirmed: bool
    page_offset: int = Field(default=0, ge=0, le=1000)


@router.post("/runs/{run_id}/annual-report")
async def attach_annual_report(run_id: str, request: Request, service: RunService = Depends(get_run_service)):
    run = service.get_run(run_id)
    if run['planner_mode'] != 'annual_update' or run['status'] not in {'COMPLETE', 'PARTIAL'}:
        raise HTTPException(409, "完成本次财报更新后才能补查 PDF。")
    user = request.state.user
    limit(service.store, 'annual-pdf:' + user['id'], 10, seconds=3600)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 4 * 1024 * 1024 + 4096:
            raise HTTPException(413, "PDF 文件不得超过 3 MB。")
        raw.extend(chunk)
    try:
        body = AnnualUpload.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, "PDF 请求格式无效。") from exc
    if not body.confirmed or not body.filename.lower().endswith('.pdf'):
        raise HTTPException(422, "请确认 PDF 对应本次研究的公司和财年。")
    if run['updated_at'] != body.expected_updated_at or run['plan_version'] != body.plan_version:
        raise HTTPException(409, "研究状态已更新，请刷新后重试。")
    if run['supplement_rounds'] >= service.settings.max_supplement_rounds:
        raise HTTPException(409, "已达到补查轮次上限。")
    pdf = await run_in_threadpool(extract, body, annual_pages=True)
    args = run['tasks'][0]['arguments']
    task = upload_task(pdf, args['symbol'], args['fiscal_year'], body.plan_version + 1, body.page_offset)
    if not task:
        raise HTTPException(422, "未找到营收或利润相关的文字。请检查是否上传了正确的章节。")
    if any(item['arguments'].get('sha256') == pdf['sha256'] and item['arguments'].get('records') == task['arguments']['records']
           for item in run['tasks']):
        raise HTTPException(409, "同一份资料已加入本次研究。")
    supplemented = service.propose_supplement(run_id, body.expected_updated_at, body.plan_version, uploaded_task=task)
    if supplemented['status'] != 'PENDING_APPROVAL':
        raise HTTPException(409, "本次研究的执行预算已用完。")
    return supplemented


@router.get("/runs/{run_id}")
async def get_run(run_id: str, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return service.get_run(run_id)


@router.post("/runs/{run_id}/revise-plan")
async def revise_plan(run_id: str, body: RevisePlanRequest, request: Request, service: RunService = Depends(get_run_service)):
    limit(service.store, 'research-create:'+request.state.user['id'], service.settings.max_run_requests_per_hour, seconds=3600)
    return await service.revise_plan(run_id, body)


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: str, request: ApprovalRequest, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return await service.approve(run_id, request)


@router.post("/runs/{run_id}/reject")
async def reject_run(run_id: str, request: RejectRequest, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return service.reject(run_id, request)


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return await service.resume(run_id)


@router.post("/runs/{run_id}/retry-failed")
async def retry_failed_run(run_id: str, request: RetryFailedRequest, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return await service.retry_failed(run_id, request)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return service.cancel(run_id)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.get_events(run_id)


@router.get('/runs/{run_id}/events/stream')
async def stream_run_events(run_id: str, request: Request, after_id: int = Query(default=0, ge=0, le=9223372036854775807), service: RunService = Depends(get_run_service)):
    try:
        cursor = max(after_id, int(request.headers.get('Last-Event-ID', '0')))
        if cursor < 0 or cursor > 9223372036854775807:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, '无效事件游标') from None

    async def stream():
        nonlocal cursor
        started = time.monotonic()
        while time.monotonic() - started < 25:
            if await request.is_disconnected():
                return
            events = service.store.fetch_all('SELECT id,event_type,data_json,created_at FROM events WHERE run_id=? AND id>? ORDER BY id LIMIT 200', (run_id, cursor))
            for event in events:
                cursor = event['id']
                yield f"id: {cursor}\nevent: research.event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            if not events and service.get_run(run_id)['status'] not in {'PLANNING','APPROVED','RUNNING'}:
                yield 'event: stream.closed\ndata: {}\n\n'
                return
            yield ': heartbeat\n\n'
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control':'no-cache, no-transform', 'X-Accel-Buffering':'no'})


@router.post('/runs/{run_id}/supplement')
async def propose_supplement(run_id: str, body: SupplementRequest, service: RunService = Depends(get_run_service)):
    return service.propose_supplement(run_id, body.expected_updated_at, body.plan_version)


@router.get('/runs/{run_id}/review')
async def research_review(run_id: str, service: RunService = Depends(get_run_service)):
    from app.services.research_review import review_research
    run = service.get_run(run_id)
    if run['planner_mode'] == 'periodic_filing' and run.get('report'):
        return run['report']['research_review']
    return review_research(run['goal'], run['tasks'], service.get_evidence(run_id), service.registry,
        service.settings.research_data_dir, run['supplement_rounds'], service.settings.max_supplement_rounds)


@router.get("/runs/{run_id}/report")
async def run_report(run_id: str, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return service.get_report(run_id)


@router.post("/runs/{run_id}/followup")
async def followup(run_id: str, body: FollowupRequest, request: Request, service: RunService = Depends(get_run_service)):
    from app.services.annual_update import AnnualScopeError
    from app.services.research_followup import answer_followup

    run = service.get_run(run_id)
    if not run.get("report") or run["status"] not in {"COMPLETE", "PARTIAL", "FAILED"}:
        raise HTTPException(409, "本轮研究完成后可以继续追问。")
    question = body.question.strip()
    if len(question) < 2:
        raise HTTPException(422, "请输入完整的追问。")
    try:
        result = answer_followup(run, service.get_evidence(run_id), question, body.previous_question)
    except AnnualScopeError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.draft:
        if not result["draft_goal"]:
            raise HTTPException(409, "当前追问没有可生成的补查计划。")
        user = request.state.user
        limit(service.store, "research-create:" + user["id"], service.settings.max_run_requests_per_hour, seconds=3600)
        result["plan"] = await service.create_run(CreateRunRequest(goal=result["draft_goal"], thread_id=run["thread_id"]),
                                                  owner_id=user["id"])
    return result


@router.get("/runs/{run_id}/evidence")
async def run_evidence(run_id: str, service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.get_evidence(run_id)


@router.get("/runs/{run_id}/tasks")
async def run_tasks(run_id: str, service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.get_run(run_id)["tasks"]


@router.get("/runs/{run_id}/checkpoints")
async def run_checkpoints(run_id: str, service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.get_checkpoints(run_id)


@router.get("/runs/{run_id}/tool-calls")
async def run_tool_calls(run_id: str, service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.get_tool_calls(run_id)


@router.get("/runs/{run_id}/memory")
async def run_memory(run_id: str, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    run = service.get_run(run_id)
    return service.get_memory(run["thread_id"])


@router.get("/threads")
async def list_threads(request: Request, service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    user = request.state.user
    return service.list_threads(user['id']) if user['kind']=='account' else []


@router.delete('/threads/{thread_id}')
def delete_thread(thread_id: str, request: Request, service: RunService = Depends(get_run_service)):
    user = request.state.user
    with service.store.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        if not con.execute('SELECT id FROM threads WHERE id=? AND owner_id=?', (thread_id, user['id'])).fetchone():
            raise HTTPException(404, '研究不存在或无访问权限')
        if con.execute("SELECT id FROM runs WHERE thread_id=? AND status IN ('PLANNING','RUNNING','APPROVED')", (thread_id,)).fetchone():
            raise HTTPException(409, '请先等待或取消正在执行的任务')
        for table in ('run_jobs', 'tool_calls', 'events', 'checkpoints', 'evidence', 'tasks'):
            con.execute(f'DELETE FROM {table} WHERE run_id IN (SELECT id FROM runs WHERE thread_id=?)', (thread_id,))
        con.execute('DELETE FROM runs WHERE thread_id=?', (thread_id,))
        con.execute('DELETE FROM memories WHERE thread_id=?', (thread_id,))
        con.execute('DELETE FROM threads WHERE id=?', (thread_id,))
    return {'ok': True}


@router.get("/tools")
async def list_tools(service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.list_tools()

