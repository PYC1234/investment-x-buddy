import json

import httpx
import pytest
from pydantic import SecretStr
from types import SimpleNamespace

from app.services import followup_selection, periodic_filings
from app.services.research_followup import answer_followup
from app.services.report_period import report_scope
from app.services.periodic_report import build_periodic_findings
from test_run_flow import api_client, build_service


def test_long_annual_pdf_prioritizes_cash_statement_and_keeps_available_reason(monkeypatch):
    text_pages = [""] * 70
    text_pages[0] = "证券代码：600519\n2025年年度报告"
    text_pages[9] = "经营活动产生的现金流量净额变动原因说明：主要是同业存款增加。"
    text_pages[63] = "合并现金流量表\n单位：元"
    text_pages[64] = "经营活动产生的现金流量净额 61,522.20 92,463.69"
    scanned = []

    def extract(index):
        scanned.append(index)
        return text_pages[index]

    reader = SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda index=index: extract(index)) for index in range(len(text_pages))],
        outline=[[SimpleNamespace(title="合并现金流量表")]],
        get_destination_page_number=lambda _: 63,
    )
    monkeypatch.setattr(periodic_filings.time, "monotonic", lambda: len(scanned))
    records, reasons = periodic_filings.extract_pdf(reader, "600519.SH", 2025, "annual", "reported", 17)
    assert records[0]["page"] == 65 and reasons[0]["page"] == 10
    data = {"records": [], "reasons": reasons}
    findings, _ = build_periodic_findings("为什么经营现金流变了？", {"id": "filing", "data": data},
                                        {"year": 2025, "kind": "annual", "coverage": "reported"})
    assert [finding["kind"] for finding in findings] == ["gap", "disclosed"]


def test_annual_followup_answers_document_and_supported_explanation_independently():
    source = "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF"
    evidence = [
        {"id": "income", "tool_name": "get_financial_summary", "is_demo": False, "data": {"fiscal_year": 2025}},
        {"id": "annual", "tool_name": "find_official_annual_report", "is_demo": False,
         "data": {"fiscal_year": 2025, "source": source, "records": [
             {"page": 9, "text": "营业收入变动原因说明：主要是酱香系列酒产品结构调整影响。"}]}},
    ]
    run = {"goal": "请对贵州茅台进行盈利能力分析", "tasks": [{"arguments": {"symbol": "600519.SH"}}],
           "report": {"annual_answers": [{"label": "管理层对营收变化的解释",
                                         "excerpt_refs": [{"evidence_id": "annual", "record_index": 0}]}]}}
    answer = answer_followup(run, evidence, "经营状态为什么会变呢？然后财报原文，我自己不能获取到原文，你能帮我获取到吗")
    assert answer["period"] == "2025 财年" and answer["draft_goal"] is None
    revenue, profit, document = answer["findings"]
    assert revenue["kind"] == "disclosed" and "产品结构调整" in revenue["statement"]
    assert revenue["excerpt_refs"] == [{"evidence_id": "annual", "record_index": 0}]
    assert profit["kind"] == "gap"
    assert document["source_links"][0]["url"] == source
    assert answer_followup(run, evidence, "下载年报 PDF")["findings"] == [document]
    assert answer_followup(run, evidence, "发给我2024年年报原文")["draft_goal"]
    repeated = answer_followup(run, evidence, "那原因呢？", history=["营收怎么变了？", "依据呢？"])
    assert repeated["findings"][0]["excerpt_refs"] == [{"evidence_id": "annual", "record_index": 0}]


def test_investment_followup_uses_current_run_market_evidence():
    run = {"tasks": [{"arguments": {"symbol": "300750.SZ"}}]}
    market = {"id": "market", "tool_name": "get_market_snapshot", "is_demo": False,
              "data": {"prices": [{"date": f"2026-01-{day:02}", "price": 99 + day} for day in range(1, 22)]}}
    valuation = {"id": "valuation", "tool_name": "get_valuation_snapshot", "is_demo": False,
                 "data": {"valuation": {"pe_ttm": 11.25, "pb": 2.5}}}
    question = "根据分析最近能投宁德时代吗"
    answer = answer_followup(run, [market, valuation], question)
    trend, multiples, gap = answer["findings"]
    assert answer["draft_goal"] is None and answer["period"] is None
    assert trend["kind"] == "computed" and "+20.00%" in trend["statement"]
    assert trend["claims"][0]["raw_value"] == 120 and trend["claims"][0]["base_value"] == 100
    assert multiples["evidence_ids"] == ["valuation"] and "PE(TTM) 11.25" in multiples["statement"]
    assert gap["kind"] == "gap" and "可比公司" in gap["statement"]
    questions = [question, "那市盈率呢？", "依据是什么？", "和历史比呢？", "那市净率呢？"]
    outcomes = [answer_followup(run, [], text, history=questions[:index], earlier_evidence=[market, valuation])
                for index, text in enumerate(questions)]
    assert outcomes[1]["findings"][0]["claims"][0]["field"] == "valuation.pe_ttm"
    assert outcomes[2]["findings"] == outcomes[1]["findings"]
    assert outcomes[3]["findings"][-1]["task"] == "历史估值区间"
    assert outcomes[3]["findings"][-1]["kind"] == "gap"
    assert outcomes[4]["findings"][0]["claims"][0]["field"] == "valuation.pb"
    assert all(item["draft_goal"] is None for item in outcomes)
    valuation["data"]["quality"] = {"usable": False}
    assert all(finding["kind"] == "gap" for finding in answer_followup(run, [valuation], question)["findings"])


def test_cash_flow_followup_checks_saved_passages_and_proposes_same_year_when_missing():
    income = {"id": "income", "tool_name": "get_financial_summary", "is_demo": False, "data": {"fiscal_year": 2025}}
    filing = {"id": "filing", "tool_name": "search_company_filings", "is_demo": False, "data": {"records": [
        {"page": 9, "fiscal_year": 2025, "text": "营业收入变动原因说明：主要是产品结构调整。"},
    ]}}
    run = {"goal": "请对贵州茅台进行估值与风险研究", "tasks": [{"arguments": {"symbol": "600519.SH"}}],
           "report": {}}
    query = "为什么经营现金流变了？"
    missing = answer_followup(run, [income, filing], query)
    assert missing["findings"][0]["kind"] == "gap"
    assert report_scope(missing["draft_goal"]) == {"year": 2025, "kind": "annual", "coverage": "reported"}

    cause = "经营活动产生的现金流量净额变动原因说明：主要是成员单位存款减少及同业\n存款增加。"
    filing["data"]["records"].append({"page": 10, "fiscal_year": 2025, "text": cause})
    result = answer_followup(run, [income, filing], query)
    assert result["draft_goal"] is None
    assert result["findings"][0]["excerpt_refs"] == [{"evidence_id": "filing", "record_index": 1}]
    assert result["findings"][0]["statement"] == "主要是成员单位存款减少及同业存款增加。"

    pages = ["证券代码：600519\n2025年年度报告", cause]
    _, reasons = periodic_filings.extract_periodic(pages, "600519.SH", 2025, "annual", "reported")
    assert reasons[0]["key"] == "operating_cash" and reasons[0]["page"] == 2


def test_pronoun_in_investment_question_reuses_annual_cash_flow_and_citation():
    run = {"goal": "贵州茅台 2025 年经营现金流为什么下降？", "tasks": [{"arguments": {"symbol": "600519.SH"}}]}
    filing = {"id": "annual", "tool_name": periodic_filings.PERIODIC_TOOL, "is_demo": False, "data": {
        "fiscal_year": 2025, "report_kind": "annual", "coverage": "reported", "period": "2025 年年报",
        "source": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
        "records": [{"key": "operating_cash", "current": 61522000000, "previous": 92464000000,
                     "page": 65, "period": "2025 年 1–12 月", "comparison_period": "2024 年 1–12 月",
                     "basis": "合并现金流量表", "unit": "元"}],
        "reasons": [{"key": "operating_cash", "page": 10, "text": "成员单位存款减少及不可随时支取的同业存款增加。"}],
    }}
    for question in ["建议投他吗", "建议买入吗？", "值得投资吗？"]:
        answer = answer_followup(run, [filing], question)
        cash, explanation, interpretation, gap = answer["findings"]
        assert "615.22" in cash["statement"] and cash["claims"][0]["page"] == 65
        assert explanation["excerpt_refs"][0]["collection"] == "reasons"
        assert "销售收现" in interpretation["statement"] and gap["kind"] == "gap"
        assert "暂时无法判断" in answer["message"]
        assert answer["draft_kind"] == "market" and "600519.SH" in answer["draft_goal"]
    market = {"id": "market", "tool_name": "get_market_snapshot", "is_demo": False, "data": {}}
    valuation = {"id": "valuation", "tool_name": "get_valuation_snapshot", "is_demo": False,
                 "data": {"valuation": {"pe_ttm": 22, "pb": 6.8}}}
    updated = answer_followup(run, [market, valuation], "那现在呢？", history=["建议投他吗"], earlier_evidence=[filing])
    assert updated["draft_goal"] is None
    assert updated["findings"][0]["evidence_ids"] == ["annual"]
    assert any(finding["evidence_ids"] == ["valuation"] for finding in updated["findings"])
    newer = {**filing, "id": "newer", "data": {**filing["data"], "fiscal_year": 2026, "period": "2026 年年报"}}
    recalled = answer_followup(run, [newer], "刚才那个数字的依据是什么？", earlier_evidence=[filing],
                               focus={"topics": ["financial:operating_cash"], "evidence_ids": ["annual"]})
    assert recalled["period"] == "2025 年年报" and recalled["findings"][0]["evidence_ids"] == ["annual"]


@pytest.mark.anyio
async def test_model_can_only_select_a_verifiable_finding_from_the_same_conversation(monkeypatch):
    snapshot = {"task": "估值快照", "statement": "PE(TTM) 为样本记录所列倍数。", "evidence_ids": ["real"]}
    unsupported = {"task": "其它结论", "statement": "私有摘录", "evidence_ids": ["uploaded"]}
    runs = [{"report": {"findings": [unsupported, snapshot]}}]
    evidence = [{"id": "real", "tool_name": "get_valuation_snapshot", "is_demo": False, "data": {}},
                {"id": "uploaded", "tool_name": "read_uploaded_annual_report", "is_demo": False, "data": {}}]
    settings = SimpleNamespace(deepseek_base_url="https://model.invalid", deepseek_api_key=SecretStr("test-only"), deepseek_model="test")
    sent = []
    selected = [0]

    def model(request):
        sent.append(json.loads(json.loads(request.content)["messages"][1]["content"]))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"ids": selected})}}]})

    client_factory = httpx.AsyncClient
    monkeypatch.setattr(followup_selection.httpx, "AsyncClient", lambda **_: client_factory(transport=httpx.MockTransport(model)))
    answer = await followup_selection.select_findings("把有依据的那条讲出来", ["看估值"], runs, evidence, settings)
    assert answer == [snapshot]
    assert sent[0]["recent_questions"] == ["看估值"] and len(sent[0]["findings"]) == 1
    selected[:] = [1]
    assert not await followup_selection.select_findings("再看一条", [], runs, evidence, settings)


def test_interim_extraction_keeps_periods_and_pages_separate():
    pages = [
        "证券代码：600519\n2026 年第三季度报告\n主要会计数据和财务指标\n单位：元\n"
        "本报告期 年初至报告期末\n营业收入 40,200.00 3.08 130,900.00 1.96",
        "主要会计数据、财务指标发生变动的情况、原因\n"
        "经营活动产生的现金流\n量净额 120.07\n主要是同业存款到期收回。",
        "合并资产负债表\n单位：元 币种：人民币\n货币资金 49,926.81 51,690.61",
        "合并利润表\n单位：元 币种：人民币\n一、营业总收入 133,283.65 130,903.89\n"
        "其中：营业收入 130,970.74 128,453.70",
        "合并现金流量表\n单位：元 币种：人民币\n销售商品、提供劳务收到的现金 143,522.75 138,791.72",
        "经营活动产生的现金流量净额 84,058.98 38,196.80",
    ]
    rows, reasons = periodic_filings.extract_periodic(pages, "600519.SH", 2026, "q3", "reported")
    indexed = {row["key"]: row for row in rows}
    assert indexed["revenue"]["current"] == 130970.74
    assert indexed["total_revenue"]["current"] == 133283.65
    assert indexed["money"]["comparison_period"] == "2025 年 12 月末"
    assert indexed["operating_cash"]["comparison_period"] == "2025 年 1–9 月"
    assert indexed["operating_cash"]["page"] == 6 and reasons[0]["page"] == 2
    rows, reasons = periodic_filings.extract_periodic(pages, "600519.SH", 2026, "q3", "single")
    assert {r["key"] for r in rows} == {"revenue", "money"}
    assert next(r for r in rows if r["key"] == "revenue")["current"] == 40200
    assert reasons == []
    assert report_scope("最新完整财年茅台财报")["kind"] == "annual"
    assert report_scope("茅台最近经营得怎么样")["kind"] == "latest"
    assert report_scope("茅台2026年半年报")["kind"] == "h1"
    pages[3] = pages[3].replace("合并利润表", "2、合并年初到报告期末利润表").replace("单位：元", "单位：千元")
    pages[4] = pages[4].replace("合并现金流量表", "3、合并年初到报告期末现金流量表").replace("单位：元", "单位：千元")
    numbered, _ = periodic_filings.extract_periodic(pages, "600519.SH", 2026, "q3", "reported")
    assert next(row for row in numbered if row["key"] == "revenue")["current"] == 130970740
    assert next(row for row in numbered if row["key"] == "operating_cash")["current"] == 84058980


@pytest.mark.anyio
async def test_followup_reuses_evidence_and_new_period_requires_approval(monkeypatch, tmp_path):
    settings, service = build_service(tmp_path / "followup.db")
    calls = []

    def read(args):
        calls.append(args)
        records = [{
            "key": key, "current": current, "previous": previous, "label": label, "basis": "合并现金流量表",
            "page": page, "period": "2026 年 1–9 月", "comparison_period": "2025 年 1–9 月", "unit": "元",
        } for key, current, previous, label, page in [
            ("sales_cash", 143522752519.23, 138791719991.59, "销售收现", 10),
            ("operating_cash", 84058979832.29, 38196802155.27, "经营现金流净额", 11),
        ]]
        return {"symbol": args.symbol, "fiscal_year": 2026, "report_kind": "q3", "period": "2026 年三季报",
                "dataset": "periodic_filing", "coverage": args.coverage, "is_demo": False,
                "source": "https://static.cninfo.com.cn/finalpage/2026-10-31/1225649896.PDF", "records": records,
                "reasons": [{"key": "operating_cash", "page": 3, "text": "主要是同业存款到期收回。"}],
                "quality": {"status": "WARN", "usable": True, "issues": []}}

    monkeypatch.setattr(periodic_filings, "read_periodic_filing", read)
    periodic_filings.register_periodic_filings(service.registry)
    async with await api_client(settings, service) as client:
        run = (await client.post("/api/v1/runs", json={"goal": "贵州茅台2026年三季报的销售收现和经营现金流"})).json()
        path = f"/api/v1/runs/{run['id']}"
        assert run["status"] == "PENDING_APPROVAL" and calls == []
        approval = await client.post(path + "/approve", json={"plan_version": 1, "allowed_tools": [periodic_filings.PERIODIC_TOOL]})
        assert approval.json()["status"] == "COMPLETE", approval.text
        report = service.get_report(run["id"])
        assert report["period"] == "2026 年三季报"
        assert report["findings"][0]["kind"] == "computed"
        assert report["findings"][0]["claims"][1]["base_value"] == 38196802155.27

        answer = (await client.post(path + "/followup", json={"question": "经营现金流为什么增长？"})).json()
        assert any(finding.get("excerpt_refs", [{}])[0].get("collection") == "reasons" for finding in answer["findings"])
        assert len(calls) == 1 and answer["draft_goal"] is None
        # Omit browser history to verify the backend can resume from the actual previous answer.
        recalled = (await client.post(path + "/followup", json={"question": "刚才那个数据怎么算的？"})).json()
        assert recalled["findings"][0]["claims"][0]["page"] == 11
        assert "经营" in recalled["findings"][0]["task"]
        assert any(claim.get("base_value") == 38196802155.27 for claim in recalled["findings"][0]["claims"])
        causes = (await client.post(path + "/followup", json={"question": "为啥会变成这样？"})).json()
        assert any(finding.get("excerpt_refs", [{}])[0].get("collection") == "reasons" for finding in causes["findings"])
        await client.post(path + "/followup", json={"question": "销售收现是多少？"})
        switched = (await client.post(path + "/followup", json={"question": "它的数据出处在哪？"})).json()
        assert switched["findings"][0]["claims"][0]["page"] == 10
        investment = (await client.post(path + "/followup", json={"question": "建议投他吗", "draft": True})).json()
        assert investment["plan"]["status"] == "PENDING_APPROVAL" and len(calls) == 1
        assert service.get_tool_calls(investment["plan"]["id"]) == []
        assert investment["plan"]["thread_id"] == run["thread_id"]
        assert {task["tool_name"] for task in investment["plan"]["tasks"]} == {"get_market_snapshot", "get_valuation_snapshot"}
        assert all(task["arguments"]["symbol"] == "600519.SH" for task in investment["plan"]["tasks"])
        distinct = await client.post(path + "/followup", json={"question": "招商银行的经营现金流呢？"})
        assert distinct.status_code == 422
        question = {"question": "2025年三季报的经营现金流呢？"}
        preview = (await client.post(path + "/followup", json=question)).json()
        assert preview["draft_goal"] and "plan" not in preview
        result = (await client.post(path + "/followup", json={**question, "draft": True})).json()
        assert result["plan"]["thread_id"] == run["thread_id"]
        assert result["plan"]["status"] == "PENDING_APPROVAL" and len(calls) == 1
        assert result["plan"]["tasks"][0]["arguments"]["year"] == 2025
