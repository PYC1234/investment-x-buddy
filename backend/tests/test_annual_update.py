"""Offline annual-update regressions with synthetic provider responses and filings."""
import json
from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from app.core.errors import AppError
from app.services import fuyao
from app.services.research_sources import register_source_tools
from test_agent_upgrade import approve, planned
from test_run_flow import build_service


@pytest.fixture
def annual_service(tmp_path, monkeypatch):
    settings, service = build_service(tmp_path / "annual.db")
    settings.research_data_dir = tmp_path
    requests = []

    class Provider:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, *, params, headers):
            from httpx import Response

            symbol = params["thscode"]
            requests.append(symbol)
            years = (2023, 2024, 2025) if symbol == "600519.SH" else (2024, 2025)
            rows = [{
                "fiscal_year": year, "period_end_ms": int(datetime(year, 12, 31, tzinfo=timezone.utc).timestamp() * 1000),
                "operating_income": (year - 2000) * 10**8, "parent_holder_net_profit": (year - 2020) * 10**8,
                "net_profit": (year - 2020) * 10**8, "thscode": symbol, "currency": "CNY",
            } for year in years]
            return Response(200, json={"code": 0, "data": {
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000), "item": rows,
            }})

    monkeypatch.setattr(fuyao.httpx, "Client", Provider)
    service.registry = fuyao.build_fuyao_registry(SecretStr("test-only"))
    register_source_tools(service.registry, tmp_path)
    return service, requests


def write_filings(folder, symbol, year, *, relevant=True):
    source = {"source": "https://example.com/sample.pdf", "as_of": "2025-12-31", "basis": "合并年报"}
    rows = [
        {**source, "fiscal_year": year, "title": "盈利摘要", "page": 3,
         "text": "营业收入增加，收入变化与产品销量有关。" if relevant else "办公地址、电话及办公时间。"},
        {**source, "fiscal_year": year + 1, "title": "邻近年报", "page": 7,
         "text": "营业收入 归母净利润 盈利 毛利率 变动原因 经营情况。"},
    ]
    (folder / f"{symbol}.json").write_text(json.dumps({"symbol": symbol, "filings": rows}, ensure_ascii=False), encoding="utf-8")


@pytest.mark.anyio
@pytest.mark.parametrize(("symbol", "year"), [("600519.SH", 2024), ("300750.SZ", 2025)])
async def test_annual_update_pins_company_and_period(annual_service, symbol, year):
    service, requests = annual_service
    write_filings(service.settings.research_data_dir, symbol, year)
    run = await planned(service, f"请对 {symbol} 做 {year} 年财报更新，核对盈利变化与年报原文。")
    assert run["planner_mode"] == "annual_update"
    assert [task["tool_name"] for task in run["tasks"]] == ["get_financial_summary", "search_company_filings"]
    assert not requests

    run = await approve(service, run)
    assert run["status"] == "COMPLETE"
    assert requests == [symbol]
    evidence = {item["tool_name"]: item for item in service.get_evidence(run["id"])}
    financial = evidence["get_financial_summary"]["data"]
    assert [row["year"] for row in financial["financial_history"]] == [str(year - 1), str(year)]
    filing = evidence["search_company_filings"]
    assert [row["page"] for row in filing["data"]["records"]] == [3]
    assert all(item["data"]["symbol"] == symbol for item in evidence.values())
    assert run["report"]["research_review"]["coverage_status"] == "SCOPED_EVIDENCE_COLLECTED"
    assert any(filing["id"] in claim["evidence_ids"] for claim in run["report"]["findings"])


@pytest.mark.anyio
async def test_late_filing_import_preserves_report_year_and_requires_approval(annual_service):
    service, _ = annual_service
    run = await approve(service, await planned(service, "600519.SH 2024 年财报更新"))
    assert run["report"]["research_review"]["coverage_status"] == "LIMITED"
    assert any(item["task"] == "管理层解释" and not item["evidence_ids"] for item in run["report"]["findings"])
    write_filings(service.settings.research_data_dir, "600519.SH", 2024)
    supplement = service.propose_supplement(run["id"], run["updated_at"], run["plan_version"])
    assert supplement["status"] == "PENDING_APPROVAL"
    assert supplement["tasks"][-1]["arguments"]["fiscal_year"] == 2024
    completed = await approve(service, supplement)
    assert completed["report"]["research_review"]["coverage_status"] == "SCOPED_EVIDENCE_COLLECTED"


@pytest.mark.anyio
async def test_annual_update_does_not_replace_missing_year_with_latest(annual_service):
    service, _ = annual_service
    run = await approve(service, await planned(service, "600519.SH 2022 年财报更新"))
    assert run["status"] == "PARTIAL"
    assert not service.get_evidence(run["id"])
    assert run["tasks"][0]["arguments"]["fiscal_year"] == 2022
    assert run["report"]["research_review"]["coverage_status"] == "LIMITED"
    assert "unavailable or incomplete" in run["tasks"][0]["error"]


@pytest.mark.anyio
async def test_matching_year_without_relevant_excerpt_stays_limited(annual_service):
    service, _ = annual_service
    write_filings(service.settings.research_data_dir, "600519.SH", 2024, relevant=False)
    run = await approve(service, await planned(service, "600519.SH 2024 年度财报更新"))
    assert run["status"] == "PARTIAL"
    assert run["report"]["research_review"]["unanswered_questions"] == ["search_company_filings"]


@pytest.mark.anyio
@pytest.mark.parametrize("goal", [
    "600519.SH 2024 年财报更新与 2025 年财报更新",
    "600519.SH 2031 年财报更新",
    "600519.SH 和 300750.SZ 2024 年财报更新",
])
async def test_ambiguous_or_unsupported_scope_requires_edit(annual_service, goal):
    service, requests = annual_service
    with pytest.raises(AppError) as error:
        await planned(service, goal)
    assert error.value.status_code == 422
    assert not requests

@pytest.mark.anyio
@pytest.mark.parametrize("question", ["2025 年营收为什么变化？", "2025 年营收比 2024 年变了多少？"])
async def test_natural_annual_question_and_manual_year_revision(annual_service, question):
    from app.schemas.research import RevisePlanRequest

    service, requests = annual_service
    run = await planned(service, f"贵州茅台（600519.SH）{question}")
    assert run["planner_mode"] == "annual_update"
    assert run["tasks"][0]["arguments"]["fiscal_year"] == 2025
    assert run["tasks"][0]["arguments"]["require_fiscal_year"] is True
    revised = await service.revise_plan(run["id"], RevisePlanRequest(
        plan_version=run["plan_version"], expected_updated_at=run["updated_at"], goal=run["goal"], fiscal_year=2024,
    ))
    assert revised["id"] == run["id"] and revised["plan_version"] == 2
    assert revised["status"] == "PENDING_APPROVAL" and not requests
    assert revised["tasks"][0]["arguments"]["fiscal_year"] == 2024
    assert "2024 年营收" in revised["goal"]
    if "比" in question:
        assert "比 2023 年" in revised["goal"]


def text_pdf(text):
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=400)
    cmap = DecodedStreamObject()
    codes = "\n".join(f"<{index + 1:02X}> <{ord(char):04X}>" for index, char in enumerate(text))
    cmap.set_data(f"1 begincodespacerange\n<00> <FF>\nendcodespacerange\n{len(text)} beginbfchar\n{codes}\nendbfchar".encode())
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica'), NameObject('/ToUnicode'): writer._add_object(cmap)})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(f'BT /F1 12 Tf 20 300 Td <{bytes(range(1, len(text)+1)).hex()}> Tj ET'.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.anyio
async def test_structured_scope_and_pdf_supplement_api(annual_service):
    from httpx import AsyncClient
    from test_documents import payload
    from test_run_flow import api_client

    service, _ = annual_service
    write_filings(service.settings.research_data_dir, "300750.SZ", 2025)
    async with await api_client(service.settings, service) as client:
        availability = await client.get('/api/v1/annual-report-availability?symbol=300750.SZ&fiscal_year=2025')
        assert availability.json() == {'filing_available': True}
        response = await client.post('/api/v1/runs', json={'goal': '核对当年变化',
            'annual_scope': {'symbol': '300750.SZ', 'fiscal_year': 2025}})
        assert response.status_code == 201, response.text
        run = await approve(service, response.json())
        assert [item['status'] for item in run['report']['annual_answers']] == [
            'SUPPORTED', 'SUPPORTED', 'MISSING_EXPLANATION', 'MISSING_EXPLANATION']
        before = {item['id'] for item in service.get_evidence(run['id'])}
        path = f"/api/v1/runs/{run['id']}/annual-report"
        data = payload(text_pdf('营业收入变动原因说明：主要是销量增加。'), 'annual.pdf',
                       expected_updated_at=run['updated_at'], plan_version=1, confirmed=True, page_offset=8)
        async with AsyncClient(transport=client._transport, base_url='http://testserver') as stranger:
            token = (await stranger.post('/api/v1/auth/guest')).json()['token']
            denied = await stranger.post(path, json=data, headers={'Authorization': f'Bearer {token}'})
            assert denied.status_code == 404
        result = await client.post(path, json=data)
        assert result.status_code == 200, result.text
        next_run = result.json()
        assert next_run['status'] == 'PENDING_APPROVAL'
        assert before == {item['id'] for item in service.get_evidence(run['id'])}
        assert (await client.post(path, json=data)).status_code == 409
        finished = await approve(service, next_run)
        answers = finished['report']['annual_answers']
        assert answers[2]['status'] == 'DIRECT_EXCERPT'
        assert answers[3]['status'] == 'MISSING_EXPLANATION'
        items = {item['id']: item for item in service.get_evidence(run['id'])}
        assert before < set(items)
        upload = items[answers[2]['evidence_ids'][0]]
        assert upload['data']['records'][0]['page'] == 9


def test_topic_and_section_prioritize_direct_explanation():
    from app.services.annual_evidence import ranked_passages

    rows = [{'page': page, 'title': title, 'text': text} for page, title, text in [
        (2, '主要会计数据', '营业收入 毛利率 盈利 营业收入 营业收入 经营情况'),
        (6, '背景', '营业收入主要来自境内业务。'),
        (9, '主营业务分析', '营业收入变动原因说明：主要是产品结构调整。'),
        (10, '主营业务分析', '归母净利润下降，主要由于成本增加。'),
    ]]
    ranked = ranked_passages(rows, 1)
    assert ranked['revenue'][0]['page'] == 9
    assert ranked['profit'][0]['page'] == 10


def test_public_report_excerpts_distinguish_explanation_from_background():
    from pathlib import Path
    from app.services.annual_evidence import direct_topics, ranked_passages
    from app.services.annual_update import EARNINGS_QUERY

    root = Path(__file__).resolve().parents[2] / 'docs' / 'annual-report-samples'
    for symbol, expected_page in (('600519.SH', 9), ('300750.SZ', None)):
        data = json.loads((root / f'{symbol}.json').read_text(encoding='utf-8'))['filings']
        clutter = [{'page': pos, 'title': '经营情况', 'text': EARNINGS_QUERY}
                   for pos in (1, 2, 3)]
        candidates = clutter + data
        terms = set(EARNINGS_QUERY.split())
        baseline = sorted(candidates, key=lambda row: sum(term in row['text'] for term in terms), reverse=True)[:3]
        proposed = ranked_passages(candidates, 3)['revenue']
        def direct_pages(rows):
            return [row['page'] for row in rows if 'revenue' in direct_topics(row['text'])]
        assert direct_pages(baseline) == []
        assert direct_pages(proposed) == ([expected_page] if expected_page else [])
        assert data[0]['page'] in [row['page'] for row in proposed]
