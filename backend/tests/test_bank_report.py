import pytest
from test_run_flow import build_service, api_client
from test_fuyao import setup_provider


@pytest.mark.anyio
async def test_bank_report_discloses_missing_risk_metrics(monkeypatch, tmp_path):
    registry, calls = setup_provider(monkeypatch, expected_symbol="600036.SH")
    settings, service = build_service(tmp_path / "bank.db")
    service.registry = registry
    async with await api_client(settings, service) as client:
        r = await client.post("/api/v1/runs", json={"goal": "分析招商银行的风险"})
        run = r.json()
        assert "风险研究覆盖有限" in run["tasks"][1]["rationale"]
        r = await client.post(f"/api/v1/runs/{run['id']}/approve", json={"plan_version": 1, "allowed_tools": list(registry.names())})
        assert r.json()["status"] == "COMPLETE"
        report = service.get_report(run["id"])
        assert report["coverage_status"] == "LIMITED"
        assert "银行风险初步研究" in report["title"]
        statements = " ".join(f["statement"] for f in report["findings"])
        assert "不良贷款率" in statements and "尚未取得" in statements
        assert "北京时间" in statements and "毫秒" not in statements
        assert "现金回款" not in statements
        assert "渠道回款" not in str(report)
        assert "PB 低于 1 不自动代表低估" in str(report)
        assert len(calls) == 4
        assert all(set(f["evidence_ids"]) <= set(report["evidence_ids"]) for f in report["findings"])
