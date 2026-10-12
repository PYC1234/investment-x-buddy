"""Deterministic checks; never fetch data or infer missing financial values."""
import math
from datetime import datetime, timedelta, timezone
from typing import Any


def assess_evidence(tool_name: str, data: dict[str, Any], expected_symbol: str,
                    now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    issues: list[dict[str, str]] = []

    def issue(code: str, field: str, message: str, severity: str = "WARN") -> None:
        issues.append({"code": code, "field": field, "severity": severity, "message": message})

    def numeric(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def timestamp(value: Any, field: str, stale_days: int | None = None) -> None:
        if value is None:
            issue("TIME_MISSING", field, "来源时点未提供，不能确认数据新鲜度。")
            return
        if not numeric(value):
            issue("TIME_INVALID", field, "时间戳格式异常，不能用作研究依据。", "ERROR")
            return
        try:
            date = datetime.fromtimestamp(value / 1000, timezone.utc)
        except (ValueError, OverflowError, OSError):
            issue("TIME_INVALID", field, "时间戳超出有效范围。", "ERROR")
            return
        if date < datetime(2000, 1, 1, tzinfo=timezone.utc):
            issue("TIME_INVALID", field, "时间戳异常：应为毫秒且不早于 2000 年。", "ERROR")
        elif date > now + timedelta(minutes=5):
            issue("TIME_FUTURE", field, "来源时间晚于服务器当前时间超过 5 分钟，暂停使用该证据。", "ERROR")
        elif stale_days is not None and now - date > timedelta(days=stale_days):
            issue("TIME_STALE", field, f"来源时间距今超过 {stale_days} 个自然日，仅供历史参考；节假日或停牌需人工确认。")

    if data.get("symbol") != expected_symbol:
        issue("SYMBOL_MISMATCH", "symbol", "证据证券与获批任务不一致，暂停使用。", "ERROR")
    returned = data.get("returned_symbols") or []
    if returned and any(symbol != expected_symbol for symbol in returned):
        issue("PROVIDER_SYMBOL_MISMATCH", "returned_symbols", "供应商返回了其他证券，暂停使用。", "ERROR")
    elif not returned:
        issue("PROVIDER_SYMBOL_UNCONFIRMED", "returned_symbols", "响应未提供可核对证券字段；当前标的依据请求参数，尚未独立核验。")
    if data.get("available") is False:
        issue("DATA_UNAVAILABLE", "available", "来源未返回可用数据。", "ERROR")
    if not data.get("source"):
        issue("SOURCE_MISSING", "source", "缺少来源地址，无法定位供应商接口。", "ERROR")
    if data.get("currency") != "CNY":
        issue("CURRENCY_CONFLICT", "currency", "币种不是已约定的 CNY，禁止按人民币展示。", "ERROR")
    if any(currency != "CNY" for currency in data.get("returned_currencies", [])):
        issue("CURRENCY_CONFLICT", "returned_currencies", "供应商返回币种与 CNY 契约冲突。", "ERROR")
    timestamp(data.get("timestamp_ms"), "timestamp_ms", 7 if tool_name != "get_financial_summary" else None)
    issue("SOURCE_NOT_CROSS_CHECKED", "source", "仅作接口级质量检查，未与交易所公告或独立来源交叉核验。")

    provenance = data.get("field_provenance") or {}
    contracts = {
        "get_market_snapshot": {"snapshot.price_cny": ("CNY", "last_price"), "prices.price": ("CNY", "forward")},
        "get_financial_summary": {"financial_history.revenue": ("亿元", "operating_income"), "financial_history.profit": ("亿元", "parent_holder_net_profit")},
        "get_valuation_snapshot": {"valuation.pe_ttm": ("倍", "TTM"), "valuation.pb": ("倍", "MRQ")},
    }
    for field, (unit, basis) in contracts.get(tool_name, {}).items():
        meta = provenance.get(field)
        if not meta:
            issue("PROVENANCE_MISSING", field, "字段来源、单位或口径未记录，需人工核对。")
        elif meta.get("unit") != unit or basis not in str(meta.get("basis", "")):
            issue("BASIS_CONFLICT", field, "字段单位或统计口径与展示契约冲突，暂停使用该证据。", "ERROR")

    if tool_name == "get_market_snapshot":
        price = (data.get("snapshot") or {}).get("price_cny")
        if price is None:
            issue("PRICE_MISSING", "snapshot.price_cny", "缺少行情价格，不能形成价格结论。")
        elif not numeric(price) or price <= 0:
            issue("PRICE_INVALID", "snapshot.price_cny", "行情价格不是有效正数。", "ERROR")
        change = (data.get("snapshot") or {}).get("change_percent")
        if change is not None and not numeric(change):
            issue("CHANGE_INVALID", "snapshot.change_percent", "涨跌幅不是有效数值。", "ERROR")
        prices = data.get("prices") or []
        if not prices:
            issue("HISTORY_MISSING", "prices", "未取得历史价格序列，不能绘制走势。")
        dates = []
        for row in prices:
            try:
                date = datetime.strptime(str(row.get("date")), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if date.date() > now.astimezone(timezone(timedelta(hours=8))).date():
                    issue("HISTORY_FUTURE", "prices", "历史价格包含未来日期。", "ERROR")
                dates.append(date)
            except (ValueError, TypeError, AttributeError):
                issue("HISTORY_INVALID", "prices", "历史价格日期无法解析。", "ERROR")
                break
            if not numeric(row.get("price")) or row["price"] <= 0:
                issue("HISTORY_INVALID", "prices", "历史价格包含无效数值。", "ERROR")
                break
        if len(set(dates)) != len(dates) or dates != sorted(dates):
            issue("HISTORY_ORDER", "prices", "历史价格日期重复或未按时间排序。", "ERROR")
        if dates and (now.date() - dates[-1].date()).days > 7:
            issue("HISTORY_STALE", "prices", "最新日线超过 7 个自然日，仅供历史参考；需核验节假日或停牌。")
        if price is None and not prices:
            issue("NO_PRICE_DATA", "snapshot", "行情和历史价格均缺失。", "ERROR")
    elif tool_name == "get_valuation_snapshot":
        values = data.get("valuation") or {}
        for key in ("pe_ttm", "pb"):
            if values.get(key) is None:
                issue("VALUATION_MISSING", f"valuation.{key}", f"{key} 未提供，不能推断该项估值。")
            elif not numeric(values[key]):
                issue("VALUATION_INVALID", f"valuation.{key}", "估值倍数不是有效数值。", "ERROR")
            elif values[key] <= 0:
                issue("VALUATION_NONPOSITIVE", f"valuation.{key}", "估值倍数非正，可能涉及亏损或负净资产，不能按通常倍数解释。")
        if all(values.get(key) is None for key in ("pe_ttm", "pb")):
            issue("NO_VALUATION_DATA", "valuation", "PE 与 PB 均未取得。", "ERROR")
    elif tool_name == "get_financial_summary":
        rows = data.get("financial_history") or []
        years = []
        if not rows:
            issue("NO_FINANCIAL_DATA", "financial_history", "未取得可用营收及归母利润序列。", "ERROR")
        for row in rows:
            try:
                year = int(row.get("year"))
                years.append(year)
                if year < 2000 or year >= now.year:
                    issue("PERIOD_INVALID", "financial_history.year", "年度报表期间尚未结束或异常。", "ERROR")
                if any(not numeric(row.get(key)) for key in ("revenue", "profit")):
                    issue("FINANCIAL_INVALID", "financial_history", "营收或归母利润不是有效数值。", "ERROR")
            except (TypeError, ValueError, AttributeError):
                issue("PERIOD_INVALID", "financial_history.year", "财务年度无法解析。", "ERROR")
        if years and (len(set(years)) != len(years) or years != sorted(years)):
            issue("PERIOD_ORDER", "financial_history.year", "财务年度重复或顺序异常。", "ERROR")
        if any(b - a != 1 for a, b in zip(years, years[1:])):
            issue("PERIOD_GAP", "financial_history.year", "可用年度不连续，相邻点变化不能解释为同比。")
        if years and now.year - max(years) > 2:
            issue("FINANCIAL_STALE", "financial_history.year", "最新财务年度距今超过两年，仅供历史参考。")
        if (data.get("financials") or {}).get("roe_percent") is None:
            issue("ROE_MISSING", "financials.roe_percent", "利润表未提供 ROE 所需的完整口径，不补造指标。")
    # Deduplicate issue codes/fields while retaining deterministic display order.
    issues = list({(item["code"], item["field"]): item for item in issues}.values())
    usable = not any(item["severity"] == "ERROR" for item in issues)
    return {"version": 1, "checked_at": now.isoformat(), "status": "FAIL" if not usable else "WARN" if issues else "PASS", "usable": usable, "issues": issues,
            "policy": "接口级规则检查；7 自然日为行情陈旧提醒，不是交易日校验；不证明财务真实或结论正确。"}
