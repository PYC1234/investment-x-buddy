from typing import Any

from fastapi import APIRouter, Depends, Request, HTTPException
import json
from app.api.routes.auth import principal

from app.schemas.research import ApprovalRequest, CreateRunRequest, RejectRequest, RetryFailedRequest
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
    result = await service.create_run(request)
    service.store.execute('UPDATE threads SET owner_id=? WHERE id=? AND (owner_id IS NULL OR owner_id=?)', (user['id'], result['thread_id'], user['id']))
    return result


@router.get("/runs/{run_id}")
async def get_run(run_id: str, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return service.get_run(run_id)


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


@router.get("/runs/{run_id}/report")
async def run_report(run_id: str, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return service.get_report(run_id)


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
        for table in ('tool_calls', 'events', 'checkpoints', 'evidence', 'tasks'):
            con.execute(f'DELETE FROM {table} WHERE run_id IN (SELECT id FROM runs WHERE thread_id=?)', (thread_id,))
        con.execute('DELETE FROM runs WHERE thread_id=?', (thread_id,))
        con.execute('DELETE FROM memories WHERE thread_id=?', (thread_id,))
        con.execute('DELETE FROM threads WHERE id=?', (thread_id,))
    return {'ok': True}


@router.get("/tools")
async def list_tools(service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.list_tools()

