"""Read-only Fuyao tools. No fixture fallback; no automatic network retries."""
from datetime import datetime, timedelta, timezone
from math import isfinite
import httpx
from app.services.tools import RegisteredTool, StockArgs, FinancialArgs, ToolExecutionError, ToolRegistry

FUYAO_STATEMENTS = {
    "get_fuyao_cash_flow": ("cash-flow-statements", "cash_flows", {
        "operating_cash_flow": "act_cash_flow_net",
    }),
    "get_fuyao_balance_sheet": ("balance-sheets", "balance_sheets", {
        "total_assets": "assets_total",
        "total_liabilities": "total_debt",
        "total_equity": "holder_equity_total",
    }),
}


def build_fuyao_registry(secret):
    def get(path, params):
        try:
            with httpx.Client(timeout=8, follow_redirects=False, transport=httpx.HTTPTransport(retries=0)) as client:
                response = client.get("https://fuyao.aicubes.cn" + path, params=params, headers={"X-api-key": secret.get_secret_value()})
            if response.status_code != 200:
                raise ToolExecutionError(f"Fuyao HTTP {response.status_code}")
            body = response.json()
            if body.get("code") != 0:
                raise ToolExecutionError(f"Fuyao business code {body.get('code')}")
            data = body.get("data") or {}
            if not data.get("item"):
                raise ToolExecutionError("Fuyao returned no records")
            return data
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Fuyao request failed: {type(exc).__name__}") from None

    def base(symbol, path, data):
        returned = sorted({str(row["thscode"]).upper() for row in data["item"] if row.get("thscode")})
        currencies = sorted({str(row["currency"]).upper() for row in data["item"] if row.get("currency")})
        return {"symbol": symbol, "returned_symbols": returned, "returned_currencies": currencies, "available": True, "is_demo": False, "data_label": "FUYAO / MARKET DATA", "source": "https://fuyao.aicubes.cn" + path, "timestamp_ms": data.get("timestamp"), "retrieved_at": datetime.now(timezone.utc).isoformat(), "currency": "CNY"}

    def field(path, unit, basis):
        return {"raw_field": path, "unit": unit, "basis": basis}

    def market(args):
        path = "/api/a-share/prices/snapshot"
        data = get(path, {"thscodes": args.symbol})
        row = data["item"][0]
        end = datetime.now(timezone.utc)
        history = get("/api/a-share/prices/historical", {"thscode": args.symbol, "interval": "1d", "start": int((end-timedelta(days=365)).timestamp()*1000), "end": int(end.timestamp()*1000), "adjust": "forward"})
        history_symbols = {str(r["thscode"]).upper() for r in history["item"] if r.get("thscode")}
        result = {**base(args.symbol, path, data), "snapshot": {"price_cny": row.get("last_price"), "change_percent": row.get("price_change_ratio_pct"), "as_of": data.get("timestamp")}, "prices": [{"date": datetime.fromtimestamp(r["date_ms"]/1000, timezone(timedelta(hours=8))).strftime("%Y-%m-%d"), "price": r["close_price"]} for r in sorted(history["item"], key=lambda x:x["date_ms"]) if r.get("close_price") is not None], "adjust": "forward", "history_source": "https://fuyao.aicubes.cn/api/a-share/prices/historical", "raw_items": data["item"], "history_raw_items": history["item"], "field_provenance": {"snapshot.price_cny": field("item[0].last_price", "CNY", "last_price; 最近可用行情"), "prices.price": field("item[].close_price", "CNY", "forward; 前复权日线")}}
        result["returned_symbols"] = sorted(set(result["returned_symbols"]) | history_symbols)
        result["returned_currencies"] = sorted(set(result["returned_currencies"]) | {str(r["currency"]).upper() for r in history["item"] if r.get("currency")})
        return result

    def financial(args):
        path = "/api/a-share/financials/income-statements"
        data = get(path, {"thscode": args.symbol, "period": "annual", "limit": 5})
        rows = sorted(data["item"], key=lambda r:r["period_end_ms"])
        if args.require_fiscal_year:
            rows = [row for row in rows if str(row.get("fiscal_year")) in {str(args.fiscal_year), str(args.fiscal_year - 1)}]
            years = [str(row["fiscal_year"]) for row in rows]
            if len(years) != len(set(years)):
                raise ToolExecutionError("Annual periods are ambiguous in provider response.", retryable=False)
            if not rows or years[-1] != str(args.fiscal_year) or any(
                rows[-1].get(key) is None for key in ("operating_income", "parent_holder_net_profit")
            ):
                raise ToolExecutionError("Requested annual income statement is unavailable or incomplete.", retryable=False)
        latest = rows[-1]
        revenue = latest.get("operating_income")
        profit = latest.get("net_profit")
        return {**base(args.symbol, path, data), "fiscal_year": latest.get("fiscal_year"), "period_policy": "requested annual report and prior-year comparison" if args.require_fiscal_year else "latest available annual reports; requested fiscal_year is not a guarantee", "financials": {"roe_percent": None, "net_margin_percent": profit/revenue*100 if profit is not None and revenue else None, "revenue_growth_percent": None}, "financial_history": [{"year": str(r["fiscal_year"]), "revenue": r["operating_income"]/1e8, "profit": r["parent_holder_net_profit"]/1e8} for r in rows if r.get("operating_income") is not None and r.get("parent_holder_net_profit") is not None], "raw_items": rows, "field_provenance": {"financial_history.revenue": field("item[].operating_income", "亿元", "annual operating_income / 100000000"), "financial_history.profit": field("item[].parent_holder_net_profit", "亿元", "annual parent_holder_net_profit / 100000000")}, "missing_information": "利润表不提供 ROE；未取得资产负债表与现金流量表。财务趋势单位为亿元，利润为归母净利润。"}

    def valuation(args):
        path = "/api/a-share/valuations/snapshot"
        data = get(path, {"thscodes": args.symbol})
        row = data["item"][0]
        return {**base(args.symbol, path, data), "valuation": {"pe_ttm": row.get("pe_ttm"), "pb": row.get("pb_mrq"), "dividend_yield_percent": None}, "raw_items": data["item"], "field_provenance": {"valuation.pe_ttm": field("item[0].pe_ttm", "倍", "TTM"), "valuation.pb": field("item[0].pb_mrq", "倍", "MRQ")}, "missing_information": "PB 为 MRQ 口径；本接口不提供股息率或历史估值区间。"}

    def statement_handler(endpoint, dataset, fields):
        def execute(args):
            path = "/api/a-share/financials/" + endpoint
            data = get(path, {"thscode": args.symbol, "period": "annual", "limit": 5})
            records = []
            for row in sorted(data["item"], key=lambda item: item["period_end_ms"]):
                if str(row.get("thscode", "")).upper() != args.symbol:
                    raise ToolExecutionError("Fuyao statement stock does not match request.", retryable=False)
                period = datetime.fromtimestamp(row["period_end_ms"] / 1000, timezone(timedelta(hours=8))).date()
                values = {key: row.get(raw) for key, raw in fields.items()}
                if (period.month, period.day) != (12, 31) or not all(
                    type(value) in (int, float) and isfinite(value) for value in values.values()
                ):
                    continue
                records.append({"period": period.isoformat(), "unit": "元", "source": "https://fuyao.aicubes.cn" + path,
                                "basis": "年度合并报表", **values})
            if not records or len({row["period"] for row in records}) != len(records):
                raise ToolExecutionError("Fuyao annual statement fields missing or periods ambiguous.", retryable=False)
            return {**base(args.symbol, path, data), "dataset": dataset, "records": records,
                    "field_provenance": {f"records.{key}": field(f"item[].{raw}", "元", "年度合并报表")
                                         for key, raw in fields.items()}}
        return execute

    registry = ToolRegistry()
    def checked_handler(handler):
        def execute(args):
            try:
                return handler(args)
            except (ValueError, TypeError, KeyError, OverflowError, OSError):
                raise ToolExecutionError("Fuyao response schema invalid; no fixture fallback.") from None
        return execute
    for name, model, handler in [("get_market_snapshot", StockArgs, market), ("get_financial_summary", FinancialArgs, financial), ("get_valuation_snapshot", StockArgs, valuation)]:
        registry.register(RegisteredTool(name, "Read Fuyao market data; no demo fallback.", model, checked_handler(handler), "FUYAO / MARKET DATA"))
    for name, (endpoint, dataset, fields) in FUYAO_STATEMENTS.items():
        registry.register(RegisteredTool(name, f"Read Fuyao annual consolidated {endpoint}.", StockArgs,
                                         checked_handler(statement_handler(endpoint, dataset, fields)),
                                         "FUYAO / MARKET DATA", capability=dataset))
    return registry
