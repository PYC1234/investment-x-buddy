"""Find a scoped annual report in the public CNINFO disclosure index."""
import io
import re
import time

import httpx
from pydantic import Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.annual_evidence import direct_topics, ranked_passages
from app.services.tools import RegisteredTool, StockArgs, ToolExecutionError

OFFICIAL_FILING_TOOL = "find_official_annual_report"
INDEX = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
FILES = "https://static.cninfo.com.cn/"
MAX_PDF_BYTES = 24 * 1024 * 1024
# Previously verified official PDF for the bundled public demonstration.
KNOWN_DISCLOSURES = {("600519.SH", 2025): "finalpage/2026-04-17/1225114741.PDF"}


class OfficialFilingArgs(StockArgs):
    fiscal_year: int | None = Field(default=None, ge=2020, le=2030)


def find_official_report(args):
    if args.fiscal_year is None:
        raise ToolExecutionError("未取得可用的利润表财年，无法定位官方年报。", retryable=False)
    code, market = args.symbol.split(".")
    year = args.fiscal_year
    deadline = time.monotonic() + 12
    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            indexed = True
            try:
                response = client.post(INDEX, headers={"Referer": "https://www.cninfo.com.cn/", "User-Agent": "Mozilla/5.0"},
                                       data={"pageNum": 1, "pageSize": 30, "tabName": "fulltext",
                                             "column": {"SH": "sse", "SZ": "szse"}[market], "plate": market.lower(),
                                             "category": "category_ndbg_szsh;", "searchkey": code,
                                             "seDate": f"{year+1}-01-01~{year+1}-12-31", "isHLtitle": "false"})
                response.raise_for_status()
                announcements = response.json().get("announcements") or []
            except (httpx.HTTPError, ValueError) as exc:
                if (args.symbol, year) not in KNOWN_DISCLOSURES:
                    raise exc
                announcements = []
            for row in announcements:
                title = re.sub(r"\s+", "", row.get("announcementTitle") or "")
                path = row.get("adjunctUrl") or ""
                if (row.get("secCode") == code
                        and re.fullmatch(rf"[^<>]*{year}年年度报告(?:[（(](?:修订版|更新后)[）)])?", title)
                        and re.fullmatch(r"finalpage/\d{4}-\d{2}-\d{2}/\d+\.pdf", path, re.I)):
                    break
            else:
                path = KNOWN_DISCLOSURES.get((args.symbol, year))
                if not path:
                    raise ToolExecutionError("巨潮未找到对应公司及财年的完整年报。", retryable=False)
                title = f"{args.symbol} {year} 年年度报告"
                indexed = False
            source = FILES + path
            content = bytearray()
            with client.stream("GET", source) as pdf:
                pdf.raise_for_status()
                for chunk in pdf.iter_bytes(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > MAX_PDF_BYTES or time.monotonic() > deadline:
                        raise ToolExecutionError("年报下载超出自动补查预算。", retryable=False)

        reader = PdfReader(io.BytesIO(content))
        cover = re.sub(r"\s+", "", reader.pages[0].extract_text() or "")
        if not re.search(rf"(?<!\d){code}(?!\d)", cover) or not re.search(rf"{year}年(?:年度|度)?报告", cover):
            raise ToolExecutionError("无法从年报首页核对证券代码和财年。", retryable=False)
        records = []
        for number, page in enumerate(reader.pages[:65], 1):
            if time.monotonic() > deadline:
                break
            text = page.extract_text() or ""
            for start in range(0, min(len(text), 12000), 800):
                snippet = text[start:start+950].strip()
                if snippet and direct_topics(snippet):
                    records.append({"title": title, "source": source, "page": number, "text": snippet,
                                    "basis": "巨潮资讯披露年报 · PDF 页码"})
        ranked = ranked_passages(records, 2)
        excerpts = list({(item["page"], item["text"]): item for rows in ranked.values() for item in rows}.values())
    except (httpx.HTTPError, PdfReadError, ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        raise ToolExecutionError(f"官方年报暂不可读（{type(exc).__name__}）。") from None
    return {"symbol": args.symbol, "returned_symbols": [args.symbol], "currency": "CNY",
            "fiscal_year": year, "available": True, "is_demo": False, "dataset": "filings",
            "source": source, "data_label": "巨潮资讯 · 公开年报", "records": excerpts,
            "retrieval_method": "cninfo_index" if indexed else "verified_official_pdf",
            "quality": {"status": "WARN", "usable": True, "issues": [
                {"code": "FILING_CONTEXT", "message": "已核对年报首页的证券代码和财年，原文仍需结合上下文核对。",
                 "severity": "WARN"}]},
            "missing_information": "自动补查扫描年报前 65 页，缺少直接解释时保留缺口。"}


def register_official_filings(registry):
    registry.register(RegisteredTool(OFFICIAL_FILING_TOOL, "Find CNINFO annual filing and cite earnings excerpts.",
                                     OfficialFilingArgs, find_official_report, "CNINFO PUBLIC FILINGS"))
