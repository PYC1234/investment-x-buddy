import pytest
from app.services.symbols import resolve_symbol, SymbolResolutionError
from test_run_flow import build_service, api_client
from test_fuyao import setup_provider


@pytest.mark.parametrize("goal,expected", [
    ("分析宁德时代盈利", "300750.SZ"),
    ("分析招商银行估值", "600036.SH"),
    ("研究五粮液", "000858.SZ"),
    ("分析平安银行", "000001.SZ"),
    ("分析中国平安", "601318.SH"),
    ("分析贵州茅台", "600519.SH"),
    ("分析 600900 盈利", "600900.SH"),
    ("分析300750.sz估值", "300750.SZ"),
])
def test_resolve(goal, expected):
    assert resolve_symbol(goal) == expected


@pytest.mark.parametrize("goal", ["分析腾讯", "请研究估值", "分析茅台与宁德时代", "分析茅台 300750.SZ", "分析600036.SZ", "研究123456", "研究000001和600036"])
def test_no_silent_moutai_fallback(goal):
    with pytest.raises(SymbolResolutionError):
        resolve_symbol(goal)


@pytest.mark.anyio
async def test_other_stock_plan_approval_tools(monkeypatch, tmp_path):
    registry, calls = setup_provider(monkeypatch, expected_symbol="300750.SZ")
    settings, service = build_service(tmp_path / "other.db")
    service.registry = registry
    async with await api_client(settings, service) as client:
        run = (await client.post("/api/v1/runs", json={"goal": "分析宁德时代 300750.SZ 盈利与估值"})).json()
        assert run["status"] == "PENDING_APPROVAL" and not calls
        assert all(task["arguments"]["symbol"] == "300750.SZ" for task in run["tasks"])
        response = await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": list(registry.names())})
        assert response.json()["status"] == "COMPLETE"
        assert len(calls) == 4
        assert all(item["data"]["symbol"] == "300750.SZ" for item in service.get_evidence(run["id"]))
        invalid = await client.post("/api/v1/runs", json={"goal": "研究腾讯"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "invalid_symbol"
        assert "代码" in invalid.json()["error"]["message"]
        assert len(calls) == 4
