from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.research import ApprovalRequest, CreateRunRequest
from app.services.evidence_quality import assess_evidence
from app.services.runs import RunService
from app.services.store import SQLiteStore
from app.services.tools import RegisteredTool, StockArgs, ToolRegistry
from test_run_flow import build_service


NOW = datetime(2026, 10, 12, 6, tzinfo=timezone.utc)


def valuation():
    return {"is_demo": False, "symbol": "600519.SH", "returned_symbols": ["600519.SH"],
            "currency": "CNY", "source": "https://example.test/valuation", "timestamp_ms": NOW.timestamp() * 1000,
            "valuation": {"pe_ttm": 20, "pb": 3},
            "field_provenance": {"valuation.pe_ttm": {"unit": "倍", "basis": "TTM"}, "valuation.pb": {"unit": "倍", "basis": "MRQ"}}}


@pytest.mark.parametrize("change,code", [
    ({"timestamp_ms": (NOW + timedelta(days=1)).timestamp() * 1000}, "TIME_FUTURE"),
    ({"timestamp_ms": NOW.timestamp()}, "TIME_INVALID"),
    ({"symbol": "600036.SH"}, "SYMBOL_MISMATCH"),
    ({"returned_symbols": ["600036.SH"]}, "PROVIDER_SYMBOL_MISMATCH"),
    ({"currency": "USD"}, "CURRENCY_CONFLICT"),
    ({"returned_currencies": ["USD"]}, "CURRENCY_CONFLICT"),
    ({"valuation": {"pe_ttm": None, "pb": None}}, "NO_VALUATION_DATA"),
    ({"valuation": {"pe_ttm": "invalid", "pb": 3}}, "VALUATION_INVALID"),
    ({"field_provenance": {"valuation.pe_ttm": {"unit": "%", "basis": "TTM"}}}, "BASIS_CONFLICT"),
])
def test_invalid_evidence_is_blocked(change, code):
    data = valuation() | change
    quality = assess_evidence("get_valuation_snapshot", data, "600519.SH", NOW)
    assert quality["status"] == "FAIL" and not quality["usable"]
    assert code in {item["code"] for item in quality["issues"]}


def test_stale_missing_and_negative_values_are_disclosed_without_invention():
    data = valuation() | {"timestamp_ms": (NOW - timedelta(days=10)).timestamp() * 1000,
                          "valuation": {"pe_ttm": -2, "pb": None}}
    before = deepcopy(data)
    quality = assess_evidence("get_valuation_snapshot", data, "600519.SH", NOW)
    assert quality["usable"] and quality["status"] == "WARN"
    assert {"TIME_STALE", "VALUATION_MISSING", "VALUATION_NONPOSITIVE"} <= {item["code"] for item in quality["issues"]}
    assert data == before


def test_financial_year_gap_is_not_yoy_and_future_period_is_blocked():
    data = valuation() | {"financial_history": [{"year": "2023", "revenue": 1, "profit": 0}, {"year": "2025", "revenue": 2, "profit": 1}]}
    quality = assess_evidence("get_financial_summary", data, "600519.SH", NOW)
    assert quality["usable"]
    assert "PERIOD_GAP" in {item["code"] for item in quality["issues"]}
    data["financial_history"][-1]["year"] = "2026"
    assert not assess_evidence("get_financial_summary", data, "600519.SH", NOW)["usable"]


def test_future_or_duplicate_history_is_blocked():
    data = valuation() | {"snapshot": {"price_cny": 20}, "prices": [{"date": "2026-10-13", "price": 20}]}
    assert not assess_evidence("get_market_snapshot", data, "600519.SH", NOW)["usable"]
    data["prices"] = [{"date": "2026-10-09", "price": 20}] * 2
    assert "HISTORY_ORDER" in {item["code"] for item in assess_evidence("get_market_snapshot", data, "600519.SH", NOW)["issues"]}


@pytest.mark.anyio
async def test_quality_failure_persists_partial_report_no_normal_conclusion(tmp_path):
    settings, service = build_service(tmp_path / "quality.db")
    registry = ToolRegistry()
    registry.register(RegisteredTool("get_valuation_snapshot", "mock", StockArgs, lambda _: valuation() | {"currency": "USD"}, "FUYAO / MARKET DATA"))
    # Only valuation needed to demonstrate successful retrieval vs unusable data.
    from app.schemas.research import ResearchPlan, PlannedTask
    from app.services.planner import PlanResult
    class Planner:
        async def plan(self, goal, preferences):
            return PlanResult(ResearchPlan(research_goal=goal, tasks=[PlannedTask(title="估值", tool_name="get_valuation_snapshot", arguments={"symbol": "600519.SH"}, rationale="核验")]), "fixture")
    service = RunService(settings, service.store, registry, Planner())
    run = await service.create_run(CreateRunRequest(goal="研究贵州茅台估值"))
    result = await service.approve(run["id"], ApprovalRequest(plan_version=1, allowed_tools=["get_valuation_snapshot"]))
    assert result["status"] == "PARTIAL"
    assert result["tasks"][0]["status"] == "COMPLETED"  # request succeeded, quality did not
    report = service.get_report(run["id"])
    assert report["quality_status"] == "FAIL"
    assert "20.00" not in str(report["findings"])
    assert "已排除" in str(report["findings"])
    assert "币种" in str(report["missing_information"])
    evidence = service.get_evidence(run["id"])
    assert evidence[0]["data"]["valuation"]["pe_ttm"] == 20  # preserved for review
    assert any(event["event_type"] == "evidence.quality_checked" for event in service.get_events(run["id"]))
    restarted = RunService(settings, SQLiteStore(settings.sqlite_path), registry, Planner())
    assert restarted.get_evidence(run["id"]) == evidence
    assert restarted.get_report(run["id"]) == report
