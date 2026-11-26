"""Fetch an approved periodic filing and extract exact consolidated statement rows."""
import io
import re
import time
from datetime import date
from typing import Literal

import httpx
from pydantic import Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.official_filings import FILES, INDEX, KNOWN_DISCLOSURES, MAX_PDF_BYTES
from app.services.annual_evidence import annual_cash_explanation
from app.services.report_period import PERIOD_MONTHS, PERIOD_TITLES, current_date, period_name
from app.services.tools import RegisteredTool, StockArgs, ToolExecutionError

PERIODIC_TOOL = "read_official_periodic_report"
KNOWN_PERIODIC = {
    **{(symbol, year, "annual"): path for (symbol, year), path in KNOWN_DISCLOSURES.items()},
    ("600519.SH", 2026, "q3"): "finalpage/2026-10-31/1225649896.PDF",
    ("300750.SZ", 2026, "q3"): "finalpage/2026-10-21/1225613175.PDF",
}
CATEGORIES = {"q1": "yjdbg", "h1": "bndbg", "q3": "sjdbg", "annual": "ndbg"}
OFFICIAL_TITLES = {"q1": "第一季度报告", "h1": "半年度报告", "q3": "第三季度报告", "annual": "年度报告"}
SOURCE_LABEL = "巨潮资讯 · 定期报告"
BALANCE = {"money": "货币资金", "placements": "拆出资金", "deferred": "合同负债"}
INCOME = {"revenue": "营业收入", "total_revenue": "营业总收入", "profit": "归母净利润"}
CASH = {"sales_cash": "销售商品、提供劳务收到的现金", "operating_cash": "经营活动产生的现金流量净额",
        "cash_equivalents": "期末现金及现金等价物余额", "member_deposits": "客户存款和同业存放款项净增加额",
        "bank_deposits": "存放中央银行和同业款项净增加额"}
SECTIONS = {"合并资产负债表": BALANCE, "合并利润表": INCOME, "合并现金流量表": CASH}
STATEMENT_HEADING = re.compile(
    r"(?m)^[ \t]*(?:(?:[一二三四五六七八]+|\d+)[、.．][ \t]*)?"
    r"((?:合并|母公司)(?:年初(?:到|至)报告期末|本季度|本报告期)?(?:资产负债表|利润表|现金流量表|所有者权益变动表)|财务报表附注)[ \t]*$"
)
AMOUNT_UNITS = {"元": 1, "千元": 1000, "万元": 10000, "亿元": 100000000}
NUMBER = r"[+\-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
PAIR = rf"({NUMBER})[ \t]+({NUMBER})(?![.,\d])"
TITLE_SUFFIX = r"(?:[（(](?:修订版|更新后|更正后)[）)])?"


class PeriodicFilingArgs(StockArgs):
    year: int | None = Field(default=None, ge=2020, le=2030)
    kind: Literal["latest", "annual", "q1", "h1", "q3"]
    coverage: Literal["single", "reported"] = "reported"


def select_filing(rows, args, today):
    candidates = []
    for row in rows:
        title = re.sub(r"\s+", "", row.get("announcementTitle") or "")
        path = row.get("adjunctUrl") or ""
        match = re.fullmatch(r"finalpage/(\d{4}-\d{2}-\d{2})/\d+\.pdf", path, re.I)
        if row.get("secCode") != args.symbol[:6] or not match:
            continue
        try:
            published = date.fromisoformat(match[1])
        except ValueError:
            continue
        if published > today:
            continue
        for kind, heading in PERIOD_TITLES.items():
            match = re.fullmatch(rf"[^<>]*?(20\d{{2}})年{heading}{TITLE_SUFFIX}", title)
            if not match or args.kind not in {kind, "latest"}:
                continue
            year = int(match[1])
            if args.year not in {None, year} or (year, PERIOD_MONTHS[kind]) > (published.year, published.month):
                continue
            candidates.append((year, PERIOD_MONTHS[kind], published, kind, title, path))
    return max(candidates, default=None)


def locate_filing(client, args, today):
    _, market = args.symbol.split(".")
    start = args.year or today.year - 2
    end = min(today, date(args.year + 1, 12, 31)) if args.year else today
    category = "".join(f"category_{code}_szsh;" for kind, code in CATEGORIES.items()
                       if args.kind in {kind, "latest"})
    indexed = False
    try:
        response = client.post(INDEX, headers={"Referer": "https://www.cninfo.com.cn/", "User-Agent": "Mozilla/5.0"},
                               data={"pageNum": 1, "pageSize": 30, "tabName": "fulltext",
                                     "column": {"SH": "sse", "SZ": "szse"}[market], "plate": market.lower(),
                                     "category": category, "searchkey": args.symbol[:6],
                                     "seDate": f"{start}-01-01~{end}", "isHLtitle": "false"})
        response.raise_for_status()
        rows = response.json()["announcements"] or []
        indexed = True
    except (httpx.HTTPError, ValueError, KeyError):
        rows = []
    known = [{"secCode": symbol[:6], "announcementTitle": f"{year}年{OFFICIAL_TITLES[kind]}", "adjunctUrl": path}
             for (symbol, year, kind), path in KNOWN_PERIODIC.items() if symbol == args.symbol]
    selected = select_filing([*rows, *known], args, today)
    if not selected:
        message = "巨潮资讯查询暂不可用，请稍后重试。" if not indexed else "未找到对应报告期的完整公开财报。"
        raise ToolExecutionError(message, retryable=not indexed)
    year, _, published, kind, title, path = selected
    fallback = not any(row.get("adjunctUrl") == path for row in rows)
    return year, kind, title, FILES + path, published.isoformat(), fallback


def _compact(text):
    return re.sub(r"\s+", "", text)


def _statement_rows(text, section, fields, page, year, kind, unit):
    if unit is None:
        return []
    rows = []
    for key, label in fields.items():
        pattern = r"归属于母公司(?:所有者|股东)的净利润(?:[（(][^）)]{0,45}[）)])?" if key == "profit" else re.escape(label)
        # Spaces in Chinese text and wrapped labels vary across PDF writers.
        pattern = r"\s*".join(pattern) if key != "profit" else pattern
        searchable = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text) if key == "profit" else text
        match = re.search(rf"(?m)^[ \t]*(?:(?:[一二三四五六]+、|其中[:：]|\d+[.．])\s*)?{pattern}\s*{PAIR}", searchable)
        if not match:
            continue
        values = [float(s.replace(",", "").replace("−", "-")) * unit for s in match.groups()]
        month = PERIOD_MONTHS[kind]
        current = f"{year} 年 {month} 月末" if section == "合并资产负债表" or key == "cash_equivalents" else f"{year} 年 1–{month} 月"
        previous = (f"{year - 1} 年 12 月末" if section == "合并资产负债表"
                    else f"{year - 1} 年 {month} 月末" if key == "cash_equivalents"
                    else f"{year - 1} 年 1–{month} 月")
        rows.append({"key": key, "label": label, "basis": section, "page": page,
                     "current": values[0], "previous": values[1], "period": current, "comparison_period": previous,
                     "unit": "元", "original_unit": next(name for name, scale in AMOUNT_UNITS.items() if scale == unit),
                     "text": match[0].strip()})
    return rows


def extract_periodic(pages, symbol, year, kind, coverage):
    cover = _compact(pages[0])
    if not re.search(rf"(?<!\d){symbol[:6]}(?!\d)", pages[0]) or not re.search(rf"{year}年{PERIOD_TITLES[kind]}", cover):
        raise ToolExecutionError("无法从财报首页核对证券代码和报告期。", retryable=False)
    records, reasons = {}, {}
    section, unit = None, None
    for page, raw in enumerate(pages, 1):
        if raw is None:
            section, unit = None, None
            continue
        lines = raw.replace("\u00a0", " ")
        compact = _compact(lines)
        if kind == "annual" and (explanation := annual_cash_explanation(lines)):
            reasons.setdefault("operating_cash", {"key": "operating_cash", "label": CASH["operating_cash"],
                "basis": "公司披露的变动原因", "page": page, "text": explanation})
        if "财务指标发生变动" in compact or "变动的情况、原因" in compact:
            for key, label in {"revenue": "营业收入", "profit": "归属于上市公司股东的净利润",
                               "operating_cash": CASH["operating_cash"]}.items():
                label_pattern = r"\s*".join(label)
                match = re.search(rf"(?m)^[ \t]*{label_pattern}\s*[+\-−]?\d+(?:\.\d+)?%?\s*(主要[^。！？]{{5,260}}[。！？])", lines)
                if match:
                    reasons[key] = {"key": key, "label": label, "basis": "公司披露的变动原因",
                                    "page": page, "text": _compact(match[1])}
        headings = list(STATEMENT_HEADING.finditer(lines))
        starts = [(0, section)] + [(match.start(), re.sub(r"年初(?:到|至)报告期末", "", match[1])) for match in headings]
        for index, (start, name) in enumerate(starts):
            segment = lines[start:starts[index + 1][0] if index + 1 < len(starts) else len(lines)]
            if index:
                unit = None
            if name not in SECTIONS:
                continue
            amount_unit = re.search(r"单位[:：]\s*(?:人民币)?\s*(亿元|万元|千元|元)", segment)
            if amount_unit:
                unit = AMOUNT_UNITS[amount_unit[1]]
            for row in _statement_rows(segment, name, SECTIONS[name], page, year, kind, unit):
                records.setdefault(row["key"], row)
        section = starts[-1][1]
    if coverage == "single":
        # Interim income and cash-flow statements are normally cumulative. Keep only balance-sheet snapshots.
        records = {key: value for key, value in records.items() if key in BALANCE}
        reasons = {}
        if kind == "q3":
            summary = pages[0]
            if "本报告期" in summary and re.search(r"年初(?:到|至)报告期末", _compact(summary)):
                default_unit = re.search(r"单位[:：]\s*(?:人民币)?\s*(亿元|万元|千元|元)", summary)
                for key, label in {"revenue": "营业收入", "profit": "归属于上市公司股东的净利润"}.items():
                    pattern = r"\s*".join(label)
                    match = re.search(rf"(?m)^[ \t]*{pattern}\s*(?:[（(](亿元|万元|千元|元)[）)])?\s+"
                                      rf"({NUMBER})[ \t]+({NUMBER})%?[ \t]+({NUMBER})[ \t]+({NUMBER})%?", summary)
                    if not match:
                        continue
                    reported_unit = match[1] or (default_unit[1] if default_unit else None)
                    if reported_unit and abs(float(match[3].replace(",", ""))) < 10000:
                        records[key] = {"key": key, "label": INCOME[key], "basis": "主要会计数据和财务指标 · 本报告期",
                                        "period": f"{year} 年 7–9 月", "comparison_period": f"{year - 1} 年 7–9 月",
                                        "page": 1, "unit": "元", "original_unit": reported_unit, "text": match[0],
                                        "current": float(match[2].replace(",", "")) * AMOUNT_UNITS[reported_unit],
                                        "reported_change": float(match[3].replace(",", ""))}
    return list(records.values()), list(reasons.values())


def statement_pages(reader):
    """Prioritize the financial statements in long PDFs while preserving page numbers."""
    bookmarks = {}
    try:
        pending = list(reversed(reader.outline))
        while pending:
            entry = pending.pop()
            if isinstance(entry, list):
                pending.extend(reversed(entry))
            else:
                label = _compact(entry.title)
                if label in SECTIONS and label not in bookmarks:
                    page = reader.get_destination_page_number(entry)
                    if page is not None and page >= 0:
                        bookmarks[label] = page
    except (PdfReadError, KeyError, ValueError, TypeError):
        pass
    for label in ("合并现金流量表", "合并利润表", "合并资产负债表"):
        if label in bookmarks:
            start = bookmarks[label]
            yield from range(start, start + 4)


def extract_pdf(reader, symbol, year, kind, coverage, deadline):
    limit = min(len(reader.pages), 240)
    pages = [None] * limit
    preferred = list(range(min(14, limit)))
    if kind in {"annual", "h1"}:
        preferred.extend(statement_pages(reader))
    checked = {index for index in preferred if index < limit}
    for index in dict.fromkeys([*preferred, *range(limit)]):
        if time.monotonic() > deadline:
            break
        if index >= limit:
            continue
        if index not in checked and checked and all(pages[number] is not None for number in checked):
            records, reasons = extract_periodic(pages, symbol, year, kind, coverage)
            core = {"money", "revenue", "profit", "sales_cash", "operating_cash"}
            if coverage == "reported" and core <= {row["key"] for row in records}:
                return records, reasons
            checked.clear()
        pages[index] = reader.pages[index].extract_text() or ""
    if not pages or pages[0] is None:
        raise ToolExecutionError("财报下载后已用完本次解析预算。")
    return extract_periodic(pages, symbol, year, kind, coverage)


def read_periodic_filing(args):
    deadline = time.monotonic() + 20
    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            year, kind, title, source, published, fallback = locate_filing(client, args, current_date())
            content = bytearray()
            with client.stream("GET", source) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > MAX_PDF_BYTES or time.monotonic() > deadline:
                        raise ToolExecutionError("定期报告下载超出本次研究预算。", retryable=False)
        reader = PdfReader(io.BytesIO(content))
        records, reasons = extract_pdf(reader, args.symbol, year, kind, args.coverage, deadline)
    except (httpx.HTTPError, PdfReadError, ValueError, IndexError, OSError) as exc:
        raise ToolExecutionError(f"官方定期报告暂不可读（{type(exc).__name__}）。") from None
    issues = [{"code": "PDF_TEXT_SCOPE", "severity": "WARN", "message": "已核对 PDF 首页证券代码和报告期。只提取能识别的合并报表字段，表格与归因仍可逐页核对。"}]
    if fallback and args.year is None:
        issues.append({"code": "INDEX_FALLBACK", "severity": "WARN",
                       "message": "使用已核对过的官方披露链接，未能确认是否已有更新报告。"})
    return {"symbol": args.symbol, "fiscal_year": year, "report_kind": kind, "period": period_name(year, kind, args.coverage),
            "coverage": args.coverage, "title": title, "source": source, "published_at": published,
            "data_label": SOURCE_LABEL, "dataset": "periodic_filing", "currency": "CNY",
            "is_demo": False, "available": bool(records or reasons), "records": records, "reasons": reasons,
            "annual_cash_reason_checked": kind == "annual" and args.coverage == "reported",
            "quality": {"status": "WARN", "usable": bool(records or reasons), "issues": issues}}


def register_periodic_filings(registry):
    registry.register(RegisteredTool(PERIODIC_TOOL, "Read consolidated financial statements from a scoped CNINFO filing.",
                                     PeriodicFilingArgs, read_periodic_filing, "CNINFO PUBLIC FILINGS"))
