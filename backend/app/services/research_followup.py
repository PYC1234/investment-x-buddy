"""Answer supported follow-ups from the owned run or scope a new approval."""
import re

from app.core.errors import AppError
from app.services.annual_evidence import FILING_TOOLS, annual_cash_explanation, direct_explanation
from app.services.annual_update import annual_update_year
from app.services.periodic_filings import BALANCE, CASH, INCOME, PERIODIC_TOOL
from app.services.periodic_report import WHY, TOPICS, UNSUPPORTED_TOPICS, build_periodic_findings, requested_keys
from app.services.report_period import PERIOD_NAMES, PERIOD_PATTERN, report_scope
from app.services.report_validation import attach_validation
from app.services.symbols import ALIASES, SymbolResolutionError, resolve_symbol

SOURCE_QUESTION = r"出处|来源|哪一页|第几页|原文|证据|怎么算"
EXPLICIT_PERIOD = rf"{PERIOD_PATTERN}|(?<!\d)20\d{{2}}\s*年|全年|完整财年|年报|更新(?:一轮|资料)|现在最新"
DOCUMENT_REQUEST = r"(?:财报|年报|季报|半年报|年度报告)[^。！？；]{0,14}(?:原文|全文|PDF|链接)|(?:原文|全文|PDF)[^。！？；]{0,16}(?:获取|下载|发给|打开|链接)|(?:获取|下载|发给|打开)[^。！？；]{0,16}(?:财报|年报|季报|原文|PDF)"


def filing_document(evidence, scope):
    if scope:
        for entry in evidence:
            data = entry["data"]
            if (entry["tool_name"] in {"find_official_annual_report", PERIODIC_TOOL}
                    and str(data.get("fiscal_year")) == str(scope["year"])
                    and data.get("report_kind", "annual") == scope["kind"]
                    and str(data.get("source", "")).startswith("https://static.cninfo.com.cn/")):
                return {"task": "财报原文", "statement": "本次研究已取得对应报告期的公开财报。",
                        "kind": "disclosed", "evidence_ids": [entry["id"]],
                        "source_links": [{"label": "打开完整财报 PDF", "url": data["source"]}]}
    return {"task": "财报原文", "statement": "当前证据没有对应报告期的公开财报链接。",
            "kind": "gap", "evidence_ids": []}


def annual_explanations(report, evidence, keys, scope):
    filings = {entry["id"]: entry for entry in evidence if entry["tool_name"] in FILING_TOOLS}
    answers = {answer["label"]: answer for answer in report.get("annual_answers") or []}
    findings = []
    for topic in keys:
        label = "管理层对营收变化的解释" if topic == "revenue" else "管理层对利润变化的解释" if topic == "profit" else None
        refs = []
        if topic == "operating_cash" and scope and scope["kind"] == "annual":
            year = str(scope["year"])
            for entry in filings.values():
                data = entry["data"]
                for index, row in enumerate(data.get("records", [])):
                    if (str(row.get("fiscal_year") or data.get("fiscal_year")) == year and row.get("page")
                            and (statement := annual_cash_explanation(row.get("text", "")))):
                        refs.append(({"evidence_id": entry["id"], "record_index": index}, statement))
            label = f"{CASH[topic]}变动原因"
        for ref in answers.get(label, {}).get("excerpt_refs", []):
            entry = filings.get(ref["evidence_id"])
            rows = entry["data"].get("records", []) if entry else []
            index = ref["record_index"]
            if 0 <= index < len(rows) and (statement := direct_explanation(rows[index].get("text", ""), topic)):
                refs.append((ref, statement))
        if refs:
            ref, statement = refs[0]
            findings.append({"task": label, "statement": statement, "kind": "disclosed",
                             "excerpt_refs": [ref], "evidence_ids": [ref["evidence_id"]]})
        else:
            findings.append({"task": label or f"{(BALANCE | CASH | INCOME)[topic]}变动原因",
                             "statement": "本次财报证据未找到该项变化的直接说明。", "kind": "gap",
                             "evidence_ids": []})
    return findings


def answer_followup(run, evidence, question, previous_question=""):
    symbol = run["tasks"][0]["arguments"].get("symbol")
    if re.search(r"(?<![A-Za-z0-9])\d{6}(?!\d)", question) or any(
            alias in question.lower() for aliases in ALIASES.values() for alias in aliases):
        try:
            if resolve_symbol(question) != symbol:
                raise SymbolResolutionError("不同标的")
        except SymbolResolutionError as exc:
            raise AppError(status_code=422, code="different_followup_symbol",
                           message="本次追问沿用当前公司。研究其他公司请新建研究。") from exc

    usable = [e for e in evidence if not e["is_demo"] and e["data"].get("available", True)
              and e["data"].get("quality", {}).get("usable", True)]
    item = next((e for e in usable if e["tool_name"] == PERIODIC_TOOL), None)
    scope = ({"year": item["data"]["fiscal_year"], "kind": item["data"]["report_kind"], "coverage": item["data"]["coverage"]}
             if item else None)
    context_period = item["data"]["period"] if item else None
    if not scope:
        income = next((e for e in usable if e["tool_name"] == "get_financial_summary" and e["data"].get("fiscal_year")), None)
        if income:
            scope = {"year": int(income["data"]["fiscal_year"]), "kind": "annual", "coverage": "reported"}
            context_period = f"{scope['year']} 财年"
    explicit_keys = requested_keys(question, defaults=False)
    explains = bool(re.search(WHY, question))
    asks_document = bool(re.search(DOCUMENT_REQUEST, question, re.I))
    general_change = explains and not explicit_keys and bool(re.search(r"经营|业绩|表现", question))
    keys = (["revenue", "profit"] if general_change else explicit_keys
            or requested_keys(previous_question, defaults=False) or requested_keys(run["goal"]))
    period_text = re.sub(r"(?<!半)年报", "", question) if asks_document and scope and scope["kind"] == "annual" else question
    rescope = bool(re.search(EXPLICIT_PERIOD, period_text, re.I))
    only_source = (asks_document or bool(re.search(SOURCE_QUESTION, question))) and not explicit_keys and not explains
    if only_source and not rescope and not asks_document:
        question = (previous_question or run["goal"]) + " " + question
    goal = f"{symbol}：{question}"
    if rescope:
        if scope and scope["kind"] != "annual" and re.search(r"20\d{2}\s*年", question) and not re.search(
                rf"{PERIOD_PATTERN}|全年|财年|年报", question):
            goal += f" 同期口径{PERIOD_NAMES[scope['kind']]}"
            if scope["coverage"] == "single":
                goal += "单季"
        if not requested_keys(question, defaults=False):
            labels = BALANCE | CASH | INCOME
            goal += " " + "、".join(labels[key] for key in keys)
        requested = report_scope(goal)
        if requested is None and (year := annual_update_year(goal)):
            requested = {"year": year, "kind": "annual", "coverage": "reported"}
        if requested is None or scope is None or any(
                requested[key] is not None and requested[key] != scope[key] for key in requested):
            return {"period": context_period, "findings": [], "draft_goal": goal,
                    "message": "追问需要核对新报告期，可以先生成补查计划。"}
    if re.search(r"上季度|上个季度|下一季度|今年|去年|对比过去|近[两三四五\d]年", question):
        return {"period": context_period, "findings": [], "draft_goal": None,
                "message": "请用具体财年或报告期提出时段比较，当前证据只覆盖报告列示的期间。"}
    if not explicit_keys and not only_source and not rescope and not re.search(f"{WHY}|{UNSUPPORTED_TOPICS}", question):
        return {"period": context_period, "findings": [], "draft_goal": None,
                "message": "请明确要追问的财务指标或原文依据。"}

    findings = []
    if asks_document and only_source:
        findings = [filing_document(usable, scope)]
    elif item:
        if not explicit_keys and re.search(UNSUPPORTED_TOPICS, question, re.I):
            keys = []
        findings, _ = build_periodic_findings(question, item, scope, keys=keys)
        findings = attach_validation({"findings": findings, "missing_information": []}, usable)["findings"]
    elif not re.search(UNSUPPORTED_TOPICS, question, re.I) or re.search("估值|股价", question):
        if re.search(WHY, question):
            findings = annual_explanations(run["report"], usable, keys, scope)
        else:
            patterns = [TOPICS[k] for k in keys]
            patterns += [pattern for pattern in ("估值|PE|PB", "行情|股价") if re.search(pattern, question, re.I)]
            usable_ids = {e["id"] for e in usable}
            findings = [f for f in run["report"]["findings"]
                        if f["evidence_ids"] and set(f["evidence_ids"]) <= usable_ids
                        and any(re.search(pattern, f'{f["task"]} {f["statement"]}', re.I) for pattern in patterns)][:3]
    if asks_document and not only_source:
        findings.append(filing_document(usable, scope))
    supported = any(f.get("kind") != "gap" for f in findings)
    old_annual_cash_gap = (item and scope["kind"] == "annual" and scope["coverage"] == "reported" and explains
                           and "operating_cash" in keys and not item["data"].get("annual_cash_reason_checked")
                           and not any(reason["key"] == "operating_cash" for reason in item["data"].get("reasons", [])))
    if (item or supported) and not old_annual_cash_gap:
        message = "已从本次报告的证据中核对。" if supported else "当前报告没有支持这条追问的字段或原文。"
        if supported and any(f.get("kind") == "gap" for f in findings):
            message = "已使用本次报告回答有证据的部分。其余问题见下方缺口。"
        return {"period": context_period, "findings": findings, "draft_goal": None,
                "message": message}
    if scope and scope["year"]:
        goal += f" · {scope['year']} 年{PERIOD_NAMES[scope['kind']]}"
    draftable = bool(report_scope(goal)) and not re.search(UNSUPPORTED_TOPICS, question, re.I)
    return {"period": context_period, "findings": findings, "draft_goal": goal if draftable else None,
            "message": "当前摘录缺少直接解释。可生成补查计划，获批后查阅对应报告期的完整财报。"
                       if draftable else "当前已收集的证据无法回答这条追问。"}
