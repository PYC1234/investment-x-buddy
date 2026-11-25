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
        planned = ["get_financial_summary", "get_fuyao_cash_flow", "get_fuyao_balance_sheet"]
        assert [task["tool_name"] for task in run["tasks"]] == planned
        r = await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": planned})
        assert r.json()["status"] == "COMPLETE"
        assert len(calls) == 3
        report = service.get_report(run["id"])
        assert "盈利能力初步研究" in report["title"]
        assert "利润表" in report["executive_summary"]
        assert "估值快照" not in report["executive_summary"]
        assert len(report["evidence_ids"]) == 3
        assert report["coverage_status"] == "SCOPED_EVIDENCE_COLLECTED"
        assert "经营活动现金流量净额 4.50 亿元" in str(report)


@pytest.mark.anyio
async def test_revise_plan_before_approval(monkeypatch, tmp_path):
    registry, calls = setup_provider(monkeypatch, expected_symbol="601318.SH")
    settings, service = build_service(tmp_path / "revision.db")
    service.registry = registry
    async with await api_client(settings, service) as client:
        run = (await client.post("/api/v1/runs", json={"goal": "分析中国平安盈利能力"})).json()
        path = f"/api/v1/runs/{run['id']}"
        args = {"plan_version": 1, "expected_updated_at": run["updated_at"], "goal": "分析中国平安估值"}
        response = await client.post(path + "/revise-plan", json=args)
        assert response.status_code == 200, response.text
        revised = response.json()
        assert revised["id"] == run["id"] and revised["thread_id"] == run["thread_id"]
        assert revised["plan_version"] == 2 and revised["status"] == "PENDING_APPROVAL"
        assert revised["plan"]["research_type"] == "valuation" and calls == []
        assert (await client.post(path + "/revise-plan", json=args)).status_code == 409
        tools = [task["tool_name"] for task in revised["tasks"]]
        old_approval = await client.post(path + "/approve", json={"plan_version": 1, "allowed_tools": tools})
        assert old_approval.status_code == 409 and calls == []
        narrowed = await client.post(path + "/revise-plan", json={
            "plan_version": 2, "expected_updated_at": revised["updated_at"],
            "goal": revised["goal"], "excluded_tools": ["get_financial_summary"],
        })
        assert narrowed.status_code == 200 and calls == []
        latest = narrowed.json()
        assert latest["plan_version"] == 3
        assert [task["tool_name"] for task in latest["tasks"]] == ["get_valuation_snapshot"]
        approval = await client.post(path + "/approve", json={"plan_version": 3, "allowed_tools": ["get_valuation_snapshot"]})
        assert approval.json()["status"] == "COMPLETE"
        assert calls == ["/api/a-share/valuations/snapshot"]
