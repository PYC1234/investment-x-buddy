import json
import pytest
from app.services.runs import RunService
from app.services.store import SQLiteStore
from app.services.tools import RegisteredTool, FinancialArgs, StockArgs, ToolExecutionError, financial_summary
from test_run_flow import build_service, api_client


def flaky_service(tmp_path, *, always_fail=False, budget=8):
    settings, service = build_service(tmp_path / "retry.db", max_tool_calls=budget)
    settings.max_tool_retries = 0
    attempts = []
    def financial(args):
        attempts.append(args.symbol)
        if always_fail or len(attempts) == 1:
            raise ToolExecutionError("Mock provider timeout")
        return financial_summary(args)
    service.registry.register(RegisteredTool("get_financial_summary", "Mock flaky provider", FinancialArgs, financial))
    return settings, service, attempts


async def partial_run(client):
    r = await client.post("/api/v1/runs", json={"goal": "研究贵州茅台盈利与估值"})
    run = r.json()
    r = await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": [t["tool_name"] for t in run["tasks"]]})
    assert r.json()["status"] == "PARTIAL"
    return r.json()


def retry_body(run):
    return {"plan_version": run["plan_version"], "expected_updated_at": run["updated_at"]}


@pytest.mark.anyio
async def test_retry_after_restart_preserves_success_and_archives_report(tmp_path):
    settings, service, attempts = flaky_service(tmp_path)
    async with await api_client(settings, service) as client:
        run = await partial_run(client)
    before = service.get_evidence(run['id'])
    successful = {t['id']: t['attempts'] for t in run['tasks'] if t['status'] == 'COMPLETED'}
    restarted = RunService(settings, SQLiteStore(settings.sqlite_path), service.registry, service.planner)
    async with await api_client(settings, restarted) as client:
        r = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(run))
        assert r.status_code == 200
        result = r.json()
        assert result['status'] == 'COMPLETE'
        assert len(attempts) == 2
        assert len(restarted.get_tool_calls(run['id'])) == 4
        assert len(restarted.get_evidence(run['id'])) == 3
        assert {e['id'] for e in before} <= {e['id'] for e in restarted.get_evidence(run['id'])}
        assert all(t['attempts'] == successful[t['id']] for t in result['tasks'] if t['id'] in successful)
        assert next(t for t in result['tasks'] if t['tool_name'] == 'get_financial_summary')['attempts'] == 2
        events = restarted.get_events(run['id'])
        assert any(e['event_type'] == 'report.archived' and e['data']['report']['status'] == 'PARTIAL' for e in events)
        assert any(e['event_type'] == 'run.retry_completed' for e in events)
        assert restarted.get_checkpoints(run['id'])[-1]['state']['status'] == 'COMPLETE'
        duplicate = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(run))
        assert duplicate.status_code == 409 and len(attempts) == 2


@pytest.mark.anyio
async def test_repeated_failure_budget_and_stale_request(tmp_path):
    settings, service, attempts = flaky_service(tmp_path, always_fail=True, budget=4)
    async with await api_client(settings, service) as client:
        run = await partial_run(client)
        r = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(run))
        assert r.json()['status'] == 'PARTIAL'
        assert len(attempts) == 2
        current = r.json()
        stale = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(run))
        assert stale.status_code == 409 and stale.json()['error']['code'] == 'retry_state_changed'
        exhausted = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(current))
        assert exhausted.status_code == 409 and exhausted.json()['error']['code'] == 'retry_budget_exhausted'
        assert service.get_run(run['id'])['updated_at'] == current['updated_at']
        assert len(attempts) == 2 and len(service.get_evidence(run['id'])) == 2


@pytest.mark.anyio
async def test_retry_requires_approval_and_original_parameters(tmp_path):
    settings, service, attempts = flaky_service(tmp_path)
    async with await api_client(settings, service) as client:
        run = (await client.post('/api/v1/runs', json={'goal': '研究贵州茅台'})).json()
        r = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(run))
        assert r.status_code == 409 and not attempts
        run = await partial_run(client)
        malicious = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json={**retry_body(run), 'arguments': {'symbol': '000001.SZ'}})
        assert malicious.status_code == 422
        task = next(t for t in run['tasks'] if t['status'] == 'FAILED')
        changed = {**task['arguments'], 'symbol': '000001.SZ'}
        service.store.execute('UPDATE tasks SET arguments_json=? WHERE id=?', (json.dumps(changed), task['id']))
        r = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(run))
        assert r.status_code == 409 and r.json()['error']['code'] == 'retry_scope_changed'
        assert len(attempts) == 1


@pytest.mark.anyio
async def test_retry_with_insufficient_remaining_budget_keeps_unattempted_failures(tmp_path):
    settings, service, attempts = flaky_service(tmp_path, always_fail=True, budget=4)
    def fail_valuation(args):
        raise ToolExecutionError('Mock valuation failure')
    service.registry.register(RegisteredTool('get_valuation_snapshot', 'Mock failure', StockArgs, fail_valuation))
    async with await api_client(settings, service) as client:
        run = await partial_run(client)
        failed_before = [t for t in run['tasks'] if t['status'] == 'FAILED']
        assert len(failed_before) == 2
        r = await client.post(f"/api/v1/runs/{run['id']}/retry-failed", json=retry_body(run))
        result = r.json()
        assert result['status'] == 'PARTIAL'
        assert result['error'] == 'max_tool_calls'
        failed_after = [t for t in result['tasks'] if t['status'] == 'FAILED']
        assert len(failed_after) == 2
        valuation = next(t for t in failed_after if t['tool_name'] == 'get_valuation_snapshot')
        assert valuation['attempts'] == 1 and valuation['error'] == 'Mock valuation failure'
        assert len(service.get_tool_calls(run['id'])) == 4
        assert len(service.get_evidence(run['id'])) == 1
