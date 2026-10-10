from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.research import PlannedTask, ResearchPlan
from app.services.planner import FixturePlanner, PlanResult
from app.services.runs import RunService, get_run_service
from app.services.store import SQLiteStore
from app.services.tools import build_tool_registry


def build_service(path: Path, **overrides) -> tuple[Settings, RunService]:
    settings = Settings(
        _env_file=None,
        planner_mode="fixture",
        sqlite_path=path,
        max_tool_calls=overrides.get("max_tool_calls", 8),
        max_execution_rounds=8,
        run_timeout_seconds=10,
        max_tool_retries=1,
    )
    return settings, RunService(settings, SQLiteStore(path), build_tool_registry(), FixturePlanner())


async def api_client(settings: Settings, service: RunService) -> AsyncClient:
    app = create_app(settings)
    app.dependency_overrides[get_run_service] = lambda: service
    return AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver")


@pytest.mark.anyio
async def test_end_to_end_persists_evidence_report_checkpoint_and_memory(tmp_path: Path) -> None:
    database = tmp_path / "flow.db"
    settings, service = build_service(database)
    async with await api_client(settings, service) as client:
        created = await client.post("/api/v1/runs", json={"goal": "Analyze Kweichow Moutai profitability and valuation", "preferences": {"risk_style": "conservative"}})
        assert created.status_code == 201
        run = created.json()
        assert run["status"] == "PENDING_APPROVAL"
        run_id = run["id"]

        forbidden = await client.post(f"/api/v1/runs/{run_id}/resume")
        assert forbidden.status_code == 409

        allowed_tools = [task["tool_name"] for task in run["tasks"]]
        approved = await client.post(f"/api/v1/runs/{run_id}/approve", json={"plan_version": run["plan_version"], "allowed_tools": allowed_tools})
        assert approved.status_code == 200
        assert approved.json()["status"] == "COMPLETE"

        evidence = (await client.get(f"/api/v1/runs/{run_id}/evidence")).json()
        report = (await client.get(f"/api/v1/runs/{run_id}/report")).json()
        checkpoints = (await client.get(f"/api/v1/runs/{run_id}/checkpoints")).json()
        memory = (await client.get(f"/api/v1/runs/{run_id}/memory")).json()
        assert len(evidence) == 3
        assert set(report["evidence_ids"]) == {item["id"] for item in evidence}
        assert all(item["is_demo"] for item in evidence)
        assert any(item["after_chars"] < item["before_chars"] for item in checkpoints)
        assert memory["research_preferences"]["risk_style"] == "conservative"

    _, restarted = build_service(database)
    restored = restarted.get_run(run_id)
    assert restored["status"] == "COMPLETE"
    assert len(restarted.get_evidence(run_id)) == 3
    resumed = await restarted.resume(run_id)
    assert resumed["status"] == "COMPLETE"
    assert len(restarted.get_evidence(run_id)) == 3


@pytest.mark.anyio
async def test_fixture_failure_retries_and_returns_partial(tmp_path: Path) -> None:
    settings, service = build_service(tmp_path / "failure.db")
    async with await api_client(settings, service) as client:
        run = (await client.post("/api/v1/runs", json={"goal": "[simulate-failure] Analyze demo data"})).json()
        response = await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": [task["tool_name"] for task in run["tasks"]]})
        result = response.json()
        assert result["status"] == "PARTIAL"
        failed = [task for task in result["tasks"] if task["status"] == "FAILED"]
        assert len(failed) == 1
        assert failed[0]["attempts"] == 2
        report = (await client.get(f"/api/v1/runs/{run['id']}/report")).json()
        assert report["missing_information"]


@pytest.mark.anyio
async def test_tool_call_budget_stops_with_partial_result(tmp_path: Path) -> None:
    settings, service = build_service(tmp_path / "budget.db", max_tool_calls=1)
    async with await api_client(settings, service) as client:
        run = (await client.post("/api/v1/runs", json={"goal": "Analyze demo data"})).json()
        result = (await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": [task["tool_name"] for task in run["tasks"]]})).json()
        assert result["status"] == "PARTIAL"
        assert result["error"] == "max_tool_calls"
        assert len((await client.get(f"/api/v1/runs/{run['id']}/evidence")).json()) == 1


class InvalidPlanner:
    async def plan(self, goal: str, preferences: dict) -> PlanResult:
        return PlanResult(plan=ResearchPlan(research_goal=goal, tasks=[PlannedTask(title="Invalid", tool_name="get_market_snapshot", arguments={"symbol": "INVALID"}, rationale="Validate rejection")]), mode="mock-invalid")


@pytest.mark.anyio
async def test_model_generated_invalid_tool_arguments_are_rejected(tmp_path: Path) -> None:
    settings, service = build_service(tmp_path / "invalid.db")
    service.planner = InvalidPlanner()
    async with await api_client(settings, service) as client:
        response = await client.post("/api/v1/runs", json={"goal": "Create an invalid plan"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_plan"

