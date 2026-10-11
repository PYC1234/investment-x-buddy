import pytest
from app.services.planner import FixturePlanner
from test_run_flow import build_service, api_client
from test_fuyao import setup_provider


@pytest.mark.anyio
@pytest.mark.parametrize("goal,focus,tools", [
    ("分析茅台盈利能力", "profitability", ["get_financial_summary"]),
    ("分析宁德时代估值", "valuation", ["get_valuation_snapshot", "get_financial_summary"]),
    ("分析招商银行风险", "risk", ["get_market_snapshot", "get_financial_summary", "get_valuation_snapshot"]),
    ("分析茅台盈利与估值", "comprehensive", ["get_market_snapshot", "get_financial_summary", "get_valuation_snapshot"]),
])
async def test_goals_select_honest_scope(goal, focus, tools):
    result = await FixturePlanner().plan(goal, {})
    assert result.plan.research_type == focus
    assert [task.tool_name for task in result.plan.tasks] == tools
    assert len(result.plan.scope) == len(tools)
    assert result.plan.limitations
    assert len({task.arguments['symbol'] for task in result.plan.tasks}) == 1
    if focus == "risk":
        assert "不良贷款率" in str(result.plan.limitations)


@pytest.mark.anyio
async def test_profitability_scope_is_approved_and_reported(monkeypatch, tmp_path):
    registry, calls = setup_provider(monkeypatch)
    settings, service = build_service(tmp_path / "scope.db")
    service.registry = registry
    async with await api_client(settings, service) as client:
        run = (await client.post("/api/v1/runs", json={"goal": "分析贵州茅台盈利能力"})).json()
        assert run["status"] == "PENDING_APPROVAL" and not calls
        assert run["plan"]["research_type"] == "profitability"
        assert len(run["tasks"]) == 1
        r = await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": ["get_financial_summary"]})
        assert r.json()["status"] == "COMPLETE"
        assert len(calls) == 1
        report = service.get_report(run["id"])
        assert "盈利能力初步研究" in report["title"]
        assert "利润表" in report["executive_summary"]
        assert "估值快照" not in report["executive_summary"]
        assert len(report["evidence_ids"]) == 1
