"""Question-specific annual-report evidence and run-scoped PDF supplements."""
import re

from pydantic import Field

from app.services.tools import RegisteredTool, StockArgs

UPLOAD_TOOL = "read_uploaded_annual_report"
FILING_TOOLS = {"search_company_filings", UPLOAD_TOOL}
TOPICS = {
    "revenue": ("营业收入", "营收"),
    "profit": ("归母净利润", "归属于上市公司股东的净利润", "净利润", "利润总额"),
}
CHANGE = r"(?:变动|变化|增长|增加|减少|下降|上升|上涨|下滑|波动|同比)"
CAUSE = r"(?:原因(?:说明)?[：:]|主要(?:是|由于|因为|系|受)|得益于|由于)"
SECTIONS = r"主营业务分析|收入与成本|收入和成本分析|管理层讨论与分析|变动分析"


def direct_topics(text):
    compact = re.sub(r"\s+", "", text)
    found = []
    for key, terms in TOPICS.items():
        metric = "(?:" + "|".join(terms) + ")"
        if re.search(rf"{metric}[^。！？；;，,]{{0,20}}{CHANGE}[^。！？；;，,]{{0,20}}[，,]?{CAUSE}[：:，,]?[^。！？；;]{{3,}}", compact):
            found.append(key)
    return found


def ranked_passages(records, limit):
    ranked = {}
    for topic, terms in TOPICS.items():
        aliases = ("境外收入", "收入构成", "主营业务收入") if topic == "revenue" else ("盈利能力", "盈利情况")
        scored = []
        for row in records:
            text = re.sub(r"\s+", "", row["text"])
            if not any(term in text for term in (*terms, *aliases)):
                continue
            direct = topic in direct_topics(text)
            section = bool(re.search(SECTIONS, row.get("title", "") + text))
            scored.append((direct, section, row))
        scored.sort(key=lambda candidate: candidate[:2], reverse=True)
        ranked[topic] = [row for _, _, row in scored[:limit]]
    return ranked


class UploadedAnnualArgs(StockArgs):
    fiscal_year: int = Field(ge=2020, le=2030)
    filename: str = Field(min_length=1, max_length=180)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: list[dict] = Field(min_length=1, max_length=6)


def register_upload_tool(registry):
    def read(args):
        return {
            "available": True, "is_demo": False, "symbol": args.symbol,
            "fiscal_year": args.fiscal_year, "dataset": "filings",
            "data_label": "USER UPLOADED REPORT", "records": args.records,
            "sha256": args.sha256,
            "quality": {"status": "WARN", "usable": True, "issues": [{
                "code": "USER_PROVIDED_SCOPE", "severity": "WARN",
                "message": "上传资料由用户确认公司和报告期；文件身份与上下文需复核。",
            }]},
        }
    registry.register(RegisteredTool(UPLOAD_TOOL, "Read prepared excerpts for an approved run.",
                                     UploadedAnnualArgs, read, "USER UPLOADED REPORT"))


def upload_task(pdf, symbol, year, version, page_offset):
    rows = [{"title": pdf["filename"], "page": int(row["id"].split("-")[0][1:]) + page_offset,
             "text": row["text"], "basis": "用户确认的年度财报 PDF"} for row in pdf["pages"]]
    ranked = ranked_passages(rows, 3)
    selected = list({(row["page"], row["text"]): row for group in ranked.values() for row in group}.values())
    if not selected:
        return None
    return {
        "task_key": f"uploaded_annual_{version}", "title": "补查上传年报原文",
        "tool_name": UPLOAD_TOOL, "arguments": {"symbol": symbol, "fiscal_year": year,
            "filename": pdf["filename"], "sha256": pdf["sha256"], "records": selected},
        "rationale": "从当前研究关联的 PDF 提取有页码的盈利与营收资料。",
    }


def annual_answers(evidence, year):
    rows = [item for item in evidence if not item["is_demo"] and item["data"].get("available", True)
            and item["data"].get("quality", {}).get("usable", True) and str(item["data"].get("fiscal_year")) == str(year)]
    financial = next((item for item in rows if item["tool_name"] == "get_financial_summary"), None)
    comparable = financial and [str(row.get("year")) for row in financial["data"].get("financial_history", [])][-2:] == [str(year - 1), str(year)]
    filings = [item for item in rows if item["tool_name"] in FILING_TOOLS]

    def explanation(topic):
        matches = [{"evidence_id": item["id"], "record_index": index}
                   for item in filings for index, row in enumerate(item["data"].get("records", []))
                   if topic in direct_topics(row["text"])]
        return {
            "status": "DIRECT_EXCERPT" if matches else "MISSING_EXPLANATION",
            "evidence_ids": list(dict.fromkeys(match["evidence_id"] for match in matches)),
            "excerpt_refs": matches,
        }
    return [
        {"label": "当年营收与归母净利润", "status": "SUPPORTED" if financial else "MISSING_DATA",
         "evidence_ids": [financial["id"]] if financial else []},
        {"label": "与上年比较", "status": "SUPPORTED" if comparable else "MISSING_COMPARISON",
         "evidence_ids": [financial["id"]] if comparable else []},
        {"label": "管理层对营收变化的解释", **explanation("revenue")},
        {"label": "管理层对利润变化的解释", **explanation("profit")},
    ]
