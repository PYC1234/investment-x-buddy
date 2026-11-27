"""Answer supported follow-ups from the owned run or scope a new approval."""
import re
from math import isfinite

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
INVESTMENT_QUESTION = r"(?:能不能|可不可以|值不值得|能|可以|是否|值得|适合|该不该|要不要|应不应该|该|建议(?:我)?)(?:投资?|买入?|入手|建仓|加仓|减仓|卖出?)|(?:能不能|可不可以|值得不值得).{0,24}(?:投资?|买入?|建仓)|投资价值|能投吗|能买么"
MARKET_TOOLS = {"get_market_snapshot", "get_valuation_snapshot", "get_valuation_history", "get_peer_valuations"}
HISTORY_COMPARISON = r"历史估值|历史.{0,4}(?:区间|水平|分位)|(?:和|跟|与)历史.{0,4}比|过去.{0,8}(?:估值|市盈率|市净率)"
PEER_COMPARISON = r"(?:同业|同行|同行业|可比公司).{0,8}(?:比较|对比|比|估值)|(?:和|跟|与)(?:同业|同行)"
REFERENCE = r"刚才|前面|上面|上一[条轮个]|这项|那项|这个|那个|这条|那条|该指标|它|同一|这笔|那笔|这样"
SHORT_REFERENCE = r"(?:那|所以)?(?:为什么(?:会?[涨降跌])?|怎么会|为啥|怎么算|依据|出处|来源|是多少|怎么样|同比|(?:和|跟|与)去年比)(?:呢|是什么|在哪)?[？?。 ]*"
FOLLOWUP_WHY = rf"{WHY}|为啥|怎么会"


def answer_focus(findings, evidence):
    by_id = {entry["id"]: entry for entry in evidence if not entry["is_demo"]
             and entry["data"].get("available", True) and entry["data"].get("quality", {}).get("usable", True)}
    topics, refs = [], []
    for finding in findings:
        if finding.get("kind") in {"gap", "interpretation"}:
            continue
        ids = [ref for ref in finding["evidence_ids"] if ref in by_id]
        if not ids:
            continue
        fields = {claim["field"] for claim in finding.get("claims", [])}
        tools = {by_id[ref]["tool_name"] for ref in ids}
        keys = [f"financial:{key}" for key in requested_keys(finding["task"], defaults=False)]
        if "get_valuation_snapshot" in tools:
            keys = [f"market:{code}" for code, field in (("pe", "valuation.pe_ttm"), ("pb", "valuation.pb")) if field in fields]
        if "get_market_snapshot" in tools:
            keys.append("market:trend")
        if "get_valuation_history" in tools:
            keys.append("market:history")
        if "get_peer_valuations" in tools:
            keys.append("market:peers")
        if keys:
            topics.extend(keys)
            refs.extend(ids)
    return {"topics": list(dict.fromkeys(topics)), "evidence_ids": list(dict.fromkeys(refs))}


def market_intent(question):
    if re.search(INVESTMENT_QUESTION, question):
        return "investment"
    if re.search(HISTORY_COMPARISON, question):
        return "history"
    if re.search(PEER_COMPARISON, question):
        return "peers"
    pe = bool(re.search(r"市盈率|(?<![a-z])pe(?![a-z])", question, re.I))
    pb = bool(re.search(r"市净率|(?<![a-z])pb(?![a-z])", question, re.I))
    trend = bool(re.search(r"股价|行情|涨跌|日线|走势", question))
    if trend and (pe or pb or "估值" in question):
        return "overview"
    if "估值" in question or (pe and pb):
        return "valuation"
    if pe or pb:
        return "pe" if pe else "pb"
    if trend:
        return "trend"
    return None


def investment_followup(evidence, intent="investment"):
    by_tool = {}
    for item in evidence:
        by_tool.setdefault(item["tool_name"], item)
    if intent in {"history", "peers"}:
        tool, label = ("get_valuation_history", "历史估值区间") if intent == "history" else ("get_peer_valuations", "同业估值对比")
        saved = by_tool.get(tool)
        records = saved["data"].get("records", []) if saved else []
        if records:
            basis = "只反映已导入的样本，比较前仍需对齐估值日与指标口径。"
            if intent == "history" and (stats := saved["data"].get("statistics")):
                basis = f"导入样本有 {len(records)} 条，PE(TTM) 区间为 {stats['min_pe_ttm']:.2f} 至 {stats['max_pe_ttm']:.2f} 倍。" + basis
            findings = [{"task": label, "kind": "observed", "evidence_ids": [saved["id"]], "statement": basis}]
            message = "当前估值快照与可用的比较依据如下。"
        else:
            findings = [{"task": label, "kind": "gap", "evidence_ids": [],
                         "statement": f"本对话还没有可用的{label}数据。现有估值快照无法支持这项比较。"}]
            message = "这项比较还缺必要数据。可继续核对已有估值的口径和取数记录。"
        return {"period": None, "draft_goal": None, "message": message,
                "findings": [*investment_followup(evidence, "valuation")["findings"], *findings]}
    findings = []
    market = by_tool.get("get_market_snapshot")
    prices = market["data"].get("prices", []) if market else []
    if len(prices) >= 21:
        start, end = prices[-21], prices[-1]
        first, latest = start.get("price"), end.get("price")
        if all(type(value) in (int, float) and isfinite(value) and value > 0 for value in (first, latest)):
            change = (latest / first - 1) * 100
            period = f"{start['date']} 至 {end['date']}"
            findings.append({"task": "近 20 个交易日股价走势", "kind": "computed", "evidence_ids": [market["id"]],
                             "statement": f"{period}，本次取到的前复权收盘价从 {first:.2f} 元变为 {latest:.2f} 元，区间变动 {change:+.2f}%。",
                             "claims": [{"evidence_id": market["id"], "field": f"prices.{len(prices)-1}.price",
                                         "base_field": f"prices.{len(prices)-21}.price", "value": change,
                                         "unit": "%", "formula": "growth_percent", "basis": "前复权日线收盘字段",
                                         "source": market["data"].get("history_source"), "period": period}]})
    if not findings:
        findings.append({"task": "近期股价走势", "kind": "gap", "evidence_ids": [],
                         "statement": "现有证据缺少足够的可比日线，无法计算近 20 个交易日的涨跌。"})
    if intent not in {"investment", "overview", "trend"}:
        findings.clear()
    snapshot = by_tool.get("get_valuation_snapshot")
    if snapshot and intent != "trend":
        valuation = snapshot["data"].get("valuation", {})
        labels = {key: label for key, label in {"pe_ttm": "PE(TTM)", "pb": "PB(MRQ)"}.items()
                  if (intent, key) not in {("pe", "pb"), ("pb", "pe_ttm")}}
        claims = [{"evidence_id": snapshot["id"], "field": f"valuation.{key}", "value": value,
                   "unit": "倍", "basis": label}
                  for key, label in labels.items() if type(value := valuation.get(key)) in (int, float) and isfinite(value)]
        if claims:
            multiples = "、".join(f"{claim['basis']} {claim['value']:.2f} 倍" for claim in claims)
            findings.append({"task": "估值快照", "kind": "observed", "evidence_ids": [snapshot["id"]],
                             "statement": f"本次取数记录为 {multiples}。请结合取数时间核对。", "claims": claims})
    if intent != "trend" and not any(finding["task"] == "估值快照" for finding in findings):
        findings.append({"task": "估值快照", "kind": "gap", "evidence_ids": [],
                         "statement": "当前研究缺少该指标的可用估值快照。"})
    if intent in {"overview", "valuation"}:
        findings.append({"task": "估值判断的证据范围", "kind": "interpretation", "evidence_ids": [],
                         "statement": "估值倍数描述当前价格相对盈利和净资产的水平。判断定价是否有吸引力，还要结合可比范围、盈利持续性和取数日期。"})
    if intent == "investment":
        findings.append({"task": "投资判断还缺什么", "kind": "gap", "evidence_ids": [],
                         "statement": "要判断当前定价是否有吸引力，还需要核对历史估值区间、同口径可比公司和未来盈利能否支撑当前价格。近期价格变动与单次估值快照不足以形成买入或卖出结论。"})
    return {"period": None, "draft_goal": None,
            "message": "以下依据这段对话已收集的证据。",
            "findings": attach_validation({"findings": findings, "missing_information": []}, evidence)["findings"]}


def investment_with_financial_context(evidence, symbol):
    result = investment_followup(evidence)
    has_market = any(finding["kind"] != "gap" for finding in result["findings"])
    if not has_market:
        result["findings"] = result["findings"][-1:]
    if not {"get_market_snapshot", "get_valuation_snapshot"} <= {entry["tool_name"] for entry in evidence}:
        result.update(draft_goal=f"{symbol}：补查近期股价走势、PE(TTM)、PB(MRQ)，评估估值风险。", draft_kind="market")
    filing = next((entry for entry in evidence if entry["tool_name"] == PERIODIC_TOOL
                   and any(row["key"] == "operating_cash" for row in entry["data"].get("records", []))), None)
    if filing:
        data = filing["data"]
        scope = {"year": data["fiscal_year"], "kind": data["report_kind"], "coverage": data["coverage"]}
        findings, _ = build_periodic_findings("经营现金流", filing, scope, keys=["operating_cash"])
        verified = attach_validation({"findings": findings, "missing_information": []}, [filing])["findings"]
        if verified:
            result["findings"] = [*verified, {"task": "这项现金流证据说明什么", "kind": "interpretation",
                "evidence_ids": [filing["id"]], "statement": "经营现金流反映合并口径的资金流动。判断主营业务回款还需要看销售收现等分项，判断现在的定价还需要行情和估值证据。"}, *result["findings"]]
    result["message"] = ("已有证据可以用来做初步判断，还不足以得出买入或卖出结论。" if has_market
                         else "现有财报可以帮助判断经营情况。缺少近期行情和估值，暂时无法判断现在的价格是否值得买入。")
    return result


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


def answer_followup(run, evidence, question, previous_question="", *, history=(), earlier_evidence=(), focus=None):
    symbol = run["tasks"][0]["arguments"].get("symbol")
    if re.search(r"(?<![A-Za-z0-9])\d{6}(?!\d)", question) or any(
            alias in question.lower() for aliases in ALIASES.values() for alias in aliases):
        try:
            if resolve_symbol(question) != symbol:
                raise SymbolResolutionError("不同标的")
        except SymbolResolutionError as exc:
            raise AppError(status_code=422, code="different_followup_symbol",
                           message="本次追问沿用当前公司。研究其他公司请新建研究。") from exc

    available = [e for e in [*evidence, *earlier_evidence] if not e["is_demo"] and e["data"].get("available", True)
                 and e["data"].get("quality", {}).get("usable", True)]
    current_ids = {e["id"] for e in evidence}
    usable = [e for e in available if e["id"] in current_ids]
    history = list(history) or ([previous_question] if previous_question else [])
    context = [*reversed(history), run.get("goal", "")]
    topic_anchor = next((text for text in context if market_intent(text) or requested_keys(text, defaults=False)), run.get("goal", ""))
    market_context = market_intent(topic_anchor)
    intent = market_intent(question)
    explicit_keys = requested_keys(question, defaults=False)
    inherited_keys = []
    preferred_market = []
    if not intent and not explicit_keys and not re.search(EXPLICIT_PERIOD, question) and (
            re.search(REFERENCE, question) or re.fullmatch(SHORT_REFERENCE, question)):
        recalled = [e for e in available if e["id"] in (focus or {}).get("evidence_ids", [])]
        if recalled:
            topics = focus["topics"]
            if len(topics) == 1:
                group, topic = topics[0].split(":", 1)
                if group == "financial" and topic in TOPICS:
                    inherited_keys = [topic]
                    usable = [*recalled, *(e for e in usable if e not in recalled)]
                    anchor = (BALANCE | CASH | INCOME)[topic]
                    question = f"{anchor} {question}"
                    if re.search(FOLLOWUP_WHY, question) and not re.search(WHY, question):
                        question += " 原因"
                    market_context = None
                elif group == "market":
                    market_context = topic
                    intent = topic
                    preferred_market = recalled
            elif len(topics) > 1 and re.search(REFERENCE, question):
                labels = {**{f"financial:{key}": label for key, label in (BALANCE | CASH | INCOME).items()},
                          "market:pe": "市盈率", "market:pb": "市净率", "market:trend": "股价走势",
                          "market:history": "历史估值", "market:peers": "同业估值"}
                options = "、".join(labels[topic] for topic in topics if topic in labels)
                return {"period": None, "draft_goal": None, "findings": [],
                        "message": f"上一轮涉及 {options}。你想接着问哪一项？", "needs_disambiguation": True}
    if not intent and market_context and not explicit_keys:
        if market_context == "investment" and re.fullmatch(r"(?:那|所以)?(?:现在|这样|补完之后|补查后)(?:呢|怎么看|怎么判断)[？?。 ]*", question):
            intent = "investment"
        elif re.fullmatch(r"[那这]?(?:这些|那条|它|这条|这个|它的|它们的)?(?:依据|出处|来源|怎么算)(?:呢|是什么|在哪|在哪儿)?[？?。 ]*", question):
            intent = market_context
        elif re.fullmatch(r"(?:那|所以|主要)?(?:有哪些|有什么|这个)?风险(?:呢|是什么|有哪些|大吗)?[？?。 ]*", question):
            intent = "investment"
        elif re.fullmatch(r"(?:那|所以)?(?:为什么|怎么会)(?:呢|这样|这么高|这么低)?[？?。 ]*", question):
            if market_context == "trend":
                return {"period": None, "draft_goal": None, "message": "当前日线可以核对涨跌。", "findings": [
                    {"task": "涨跌原因", "kind": "gap", "evidence_ids": [],
                     "statement": "判断涨跌原因还需要同一时段的公告、事件或行业证据。"}]}
            intent = market_context if market_context in {"history", "peers"} else "valuation"
    if intent and not re.search(EXPLICIT_PERIOD, question) and (not explicit_keys or intent == "investment"):
        market_evidence = [*preferred_market, *(e for e in available if e not in preferred_market
                           and (e["id"] in current_ids or e["tool_name"] in MARKET_TOOLS | {PERIODIC_TOOL}))]
        if intent == "trend" and re.search(FOLLOWUP_WHY, question):
            result = investment_followup(market_evidence, intent)
            result["findings"].append({"task": "涨跌原因", "kind": "gap", "evidence_ids": [],
                                       "statement": "判断涨跌原因还需要同一时段的公告、事件或行业证据。"})
            return result
        if intent == "investment":
            return investment_with_financial_context(market_evidence, symbol)
        return investment_followup(market_evidence, intent)
    item = next((e for e in usable if e["tool_name"] == PERIODIC_TOOL), None)
    scope = ({"year": item["data"]["fiscal_year"], "kind": item["data"]["report_kind"], "coverage": item["data"]["coverage"]}
             if item else None)
    context_period = item["data"]["period"] if item else None
    if not scope:
        income = next((e for e in usable if e["tool_name"] == "get_financial_summary" and e["data"].get("fiscal_year")), None)
        if income:
            scope = {"year": int(income["data"]["fiscal_year"]), "kind": "annual", "coverage": "reported"}
            context_period = f"{scope['year']} 财年"
    explains = bool(re.search(WHY, question))
    asks_document = bool(re.search(DOCUMENT_REQUEST, question, re.I))
    general_change = explains and not explicit_keys and bool(re.search(r"经营|业绩|表现", question))
    keys = (["revenue", "profit"] if general_change and not inherited_keys else explicit_keys or inherited_keys
            or next((hits for text in context if (hits := requested_keys(text, defaults=False))), None)
            or requested_keys(run["goal"]))
    period_text = re.sub(r"(?<!半)年报", "", question) if asks_document and scope and scope["kind"] == "annual" else question
    rescope = bool(re.search(EXPLICIT_PERIOD, period_text, re.I))
    only_source = (asks_document or bool(re.search(SOURCE_QUESTION, question))) and not explicit_keys and not explains
    if only_source and not rescope and not asks_document and not inherited_keys:
        anchor = next((text for text in context if requested_keys(text, defaults=False) or re.search(WHY, text)), run["goal"])
        question = anchor + " " + question
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
    uses_filing_comparison = bool(inherited_keys and item and re.search(r"(?:和|跟|与)去年比", question))
    if not uses_filing_comparison and re.search(r"上季度|上个季度|下一季度|今年|去年|对比过去|近[两三四五\d]年", question):
        return {"period": context_period, "findings": [], "draft_goal": None,
                "message": "请用具体财年或报告期提出时段比较，当前证据只覆盖报告列示的期间。"}
    if not explicit_keys and not inherited_keys and not only_source and not rescope and not re.search(f"{WHY}|{UNSUPPORTED_TOPICS}", question):
        return {"period": context_period, "findings": [], "draft_goal": None,
                "message": "当前证据还无法确定你指的是哪一项。可以指明上文的指标或结论，我会接着这份研究回答。"}

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
