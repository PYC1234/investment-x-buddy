"""Build cited comparisons from the verified rows of one official filing."""
import math
import re

from app.services.periodic_filings import BALANCE, CASH, INCOME, PERIODIC_TOOL
from app.services.report_period import period_name


CASH_SUMMARY = ("money", "sales_cash", "operating_cash", "cash_equivalents")
EARNINGS_SUMMARY = ("revenue", "total_revenue", "profit")
TOPICS = {
    "money": r"账上现金|货币资金|账面现金", "placements": r"拆出资金", "deferred": r"合同负债|预收款",
    "sales_cash": r"销售收现|销售商品.{0,4}提供劳务|回款|收现|收款",
    "cash_equivalents": r"现金等价物|现金及现金等价物",
    "operating_cash": r"经营(?:性|活动产生的|活动)?现金流|经营活动产生的现金流量净额",
    "member_deposits": r"成员单位存款|客户存款", "bank_deposits": r"同业存款|存放中央银行|存放央行",
    "revenue": r"营业收入|营收|收入", "total_revenue": r"营业总收入|总营收", "profit": r"归母|净利润|盈利|利润",
}
WHY = r"为什么|为何|原因|归因|驱动|怎么解释|怎么回事|拆解|从哪来"
UNSUPPORTED_TOPICS = r"自由现金流|单瓶|同业比较|研报|机构观点|券商|行业|市占率|目标价|估值|股价|价格|ROE|净资产收益率|毛利率|直销|分红|经销|库存|开支|负债率"


def requested_keys(question, defaults=True):
    keys = [key for key, pattern in TOPICS.items() if re.search(pattern, question, re.I)]
    wide_cash = bool(re.search(r"(?<!经营)(?<!经营性)(?<!活动)现金流表现|现金流情况|现金流怎么样|分析现金流|现金流如何", question))
    if wide_cash or (not keys and re.search(r"现金流|现金", question)):
        keys.extend(CASH_SUMMARY)
    if keys:
        order = (*EARNINGS_SUMMARY, *CASH_SUMMARY, *BALANCE, *CASH)
        return list(dict.fromkeys(key for key in order if key in keys))
    return list(EARNINGS_SUMMARY) if defaults else []


def _claim(item, row, index, field, value, formula="identity", **extra):
    return {"evidence_id": item["id"], "field": f"records.{index}.{field}", "value": value,
            "formula": formula, "unit": row["unit"], "basis": row["basis"], "page": row["page"],
            "period": row["period"], **extra}


def build_periodic_findings(question, item, scope, *, keys=None):
    keys = requested_keys(question) if keys is None else keys
    data = item["data"] if item else {}
    rows = {row["key"]: (index, row) for index, row in enumerate(data.get("records", []))}
    reasons = {row["key"]: (index, row) for index, row in enumerate(data.get("reasons", []))}
    period = data.get("period") or period_name(**scope)
    findings = []
    reason_keys = {key for clause in re.split(r"[。！？；]", question) if re.search(WHY, clause)
                   for key in requested_keys(clause, defaults=False)}
    if not reason_keys and re.search(WHY, question):
        reason_keys = set(keys)

    def gap(label, message):
        findings.append({"task": label, "statement": message, "kind": "gap", "evidence_ids": []})

    def add_reason(key, label):
        if key in reasons and (key in reason_keys or key == "operating_cash"):
            reason_index, reason = reasons[key]
            findings.append({"task": f"{label}变动原因", "statement": reason["text"], "kind": "disclosed",
                             "evidence_ids": [item["id"]], "excerpt_refs": [
                                 {"evidence_id": item["id"], "collection": "reasons", "record_index": reason_index}]})
        elif key in reason_keys:
            gap(f"{label}变动原因", f"未找到公司对{label}变化的直接解释。")

    comparisons = []
    for key in keys:
        label = (BALANCE | CASH | INCOME)[key]
        if key not in rows:
            gap(label, f"未取得与「{period}」口径一致的{label}。")
            add_reason(key, label)
            continue
        index, row = rows[key]
        current = row["current"]
        prior = row.get("previous")
        growth = None
        basis = "较上年末" if row["basis"] == "合并资产负债表" else "同比"
        claims = [_claim(item, row, index, "current", current)]
        if prior is not None:
            claims.append(_claim(item, row, index, "previous", prior, period=row["comparison_period"]))
            if prior > 0:
                growth = (current / prior - 1) * 100
                if math.isfinite(growth):
                    claims.append(_claim(item, row, index, "current", growth, "growth_percent",
                                         base_field=f"records.{index}.previous", comparison_period=row["comparison_period"],
                                         unit="%"))
        elif "reported_change" in row:
            growth = row["reported_change"]
            claims.append(_claim(item, row, index, "reported_change", growth, unit="%",
                                 comparison_period=row["comparison_period"]))
        comparisons.append({"label": label, "period": row["period"], "comparison_period": row["comparison_period"],
                            "current": current, "previous": prior, "change": growth, "change_basis": basis,
                            "change_kind": "computed" if prior is not None else "disclosed",
                            "basis": row["basis"], "evidence_id": item["id"], "page": row["page"], "source": data["source"]})
        findings.append({"task": label, "statement": f"{row['period']}为 {current / 1e8:,.2f} 亿元"
                         + (f"，{basis}{growth:+.2f}%。" if growth is not None else "。"),
                         "kind": "disclosed", "evidence_ids": [item["id"]], "claims": claims})
        add_reason(key, label)
    if {"sales_cash", "operating_cash"} <= set(keys) and {"sales_cash", "operating_cash"} <= rows.keys():
        cash_index, cash = rows["sales_cash"]
        operating_index, operating = rows["operating_cash"]
        if cash.get("previous", 0) > 0 and operating.get("previous", 0) > 0:
            cash_change = (cash["current"] / cash["previous"] - 1) * 100
            operating_change = (operating["current"] / operating["previous"] - 1) * 100
            findings.insert(0, {"task": "现金流对照", "kind": "computed", "evidence_ids": [item["id"]],
                "statement": f"{cash['period']}，销售收现同比 {cash_change:+.2f}%，经营现金流净额同比 {operating_change:+.2f}%。两项指标口径不同。",
                "claims": [_claim(item, row, index, "current", change, "growth_percent",
                                  base_field=f"records.{index}.previous", comparison_period=row["comparison_period"], unit="%")
                           for index, row, change in ((cash_index, cash, cash_change), (operating_index, operating, operating_change))]})
    if re.search(UNSUPPORTED_TOPICS, question, re.I):
        gap("其他研究请求", "已取得的报表字段无法覆盖问题中的其他指标、来源或分析要求。")
    return findings, comparisons
