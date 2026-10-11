import httpx
import pytest
from pydantic import SecretStr
from app.services.fuyao import build_fuyao_registry
from app.services.tools import ToolExecutionError
from test_run_flow import build_service, api_client


def setup_provider(monkeypatch, fail=False):
    calls = []
    original = httpx.Client
    def respond(request):
        calls.append(request.url.path)
        assert request.headers["X-api-key"] == "test-secret"
        if fail:
            return httpx.Response(401, json={"error": "test-secret"})
        if "historical" in request.url.path:
            rows = [{"date_ms": 1735689600000, "close_price": 1400}]
        elif "income-statements" in request.url.path:
            rows = [{"fiscal_year": 2025, "period_end_ms": 1767139200000, "operating_income": 1000000000, "net_profit": 500000000, "parent_holder_net_profit": 400000000}]
        elif "valuations" in request.url.path:
            rows = [{"pe_ttm": 20, "pb_mrq": 6}]
        else:
            rows = [{"last_price": 1450, "price_change_ratio_pct": 1.2}]
        return httpx.Response(200, json={"code": 0, "data": {"timestamp": 1767139200000, "item": rows}})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(timeout=8, transport=httpx.MockTransport(respond)))
    return build_fuyao_registry(SecretStr("test-secret")), calls


@pytest.mark.anyio
async def test_real_provider_pipeline_with_mock_http(monkeypatch, tmp_path):
    registry, calls = setup_provider(monkeypatch)
    settings, service = build_service(tmp_path / "real.db")
    service.registry = registry
    async with await api_client(settings, service) as client:
        run = (await client.post("/api/v1/runs", json={"goal": "分析贵州茅台估值"})).json()
        assert not calls
        result = await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": list(registry.names())})
        assert result.json()["status"] == "COMPLETE"
        assert len(calls) == 4
        evidence = service.get_evidence(run["id"])
        assert all(not item["is_demo"] for item in evidence)
        market = next(item["data"] for item in evidence if item["tool_name"] == "get_market_snapshot")
        assert market["prices"][0]["price"] == 1400
        financial = next(item["data"] for item in evidence if item["tool_name"] == "get_financial_summary")
        assert financial["financial_history"][0]["revenue"] == 10
        assert financial["financials"]["roe_percent"] is None
        report = service.get_report(run["id"])
        assert "DEMO DATA" not in str(report)
        assert "1,450" in str(report) and "20.00" in str(report)
        assert "test-secret" not in str(report) + str(evidence)
        _, restarted = build_service(tmp_path / "real.db")
        assert restarted.get_evidence(run["id"]) == evidence


def test_auth_failure_redacted_no_fallback(monkeypatch):
    registry, calls = setup_provider(monkeypatch, fail=True)
    with pytest.raises(ToolExecutionError, match="Fuyao HTTP 401") as error:
        registry.execute("get_valuation_snapshot", registry.validate("get_valuation_snapshot", {"symbol": "600519.SH"}))
    assert "test-secret" not in str(error.value)
    assert len(calls) == 1
