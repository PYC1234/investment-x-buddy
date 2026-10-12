from typing import Any

from fastapi import APIRouter, Depends

from app.schemas.research import ApprovalRequest, CreateRunRequest, RejectRequest, RetryFailedRequest
from app.services.runs import RunService, get_run_service


router = APIRouter(tags=["research-runs"])


@router.post("/runs", status_code=201)
async def create_run(request: CreateRunRequest, service: RunService = Depends(get_run_service)) -> dict[str, Any]:
    return await service.create_run(request)


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
async def list_threads(service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.list_threads()


@router.get("/tools")
async def list_tools(service: RunService = Depends(get_run_service)) -> list[dict[str, Any]]:
    return service.list_tools()

