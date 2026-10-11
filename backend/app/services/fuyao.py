"""Read-only Fuyao tools. No fixture fallback; no automatic network retries."""
from datetime import datetime, timedelta, timezone
import httpx
from app.services.tools import RegisteredTool, StockArgs, FinancialArgs, ToolExecutionError, ToolRegistry


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
        return {"symbol": symbol, "available": True, "is_demo": False, "data_label": "FUYAO / MARKET DATA", "source": "https://fuyao.aicubes.cn" + path, "timestamp_ms": data.get("timestamp"), "retrieved_at": datetime.now(timezone.utc).isoformat(), "currency": "CNY"}

    def market(args):
        path = "/api/a-share/prices/snapshot"
        data = get(path, {"thscodes": args.symbol})
        row = data["item"][0]
        end = datetime.now(timezone.utc)
        history = get("/api/a-share/prices/historical", {"thscode": args.symbol, "interval": "1d", "start": int((end-timedelta(days=365)).timestamp()*1000), "end": int(end.timestamp()*1000), "adjust": "forward"})
        return {**base(args.symbol, path, data), "snapshot": {"price_cny": row.get("last_price"), "change_percent": row.get("price_change_ratio_pct"), "as_of": data.get("timestamp")}, "prices": [{"date": datetime.fromtimestamp(r["date_ms"]/1000, timezone(timedelta(hours=8))).strftime("%Y-%m-%d"), "price": r["close_price"]} for r in sorted(history["item"], key=lambda x:x["date_ms"]) if r.get("close_price") is not None], "adjust": "forward", "history_source": "https://fuyao.aicubes.cn/api/a-share/prices/historical"}

    def financial(args):
        path = "/api/a-share/financials/income-statements"
        data = get(path, {"thscode": args.symbol, "period": "annual", "limit": 5})
        rows = sorted(data["item"], key=lambda r:r["period_end_ms"])
        latest = rows[-1]
        revenue = latest.get("operating_income")
        profit = latest.get("net_profit")
        return {**base(args.symbol, path, data), "fiscal_year": latest.get("fiscal_year"), "period_policy": "latest available annual reports; requested fiscal_year is not a guarantee", "financials": {"roe_percent": None, "net_margin_percent": profit/revenue*100 if profit is not None and revenue else None, "revenue_growth_percent": None}, "financial_history": [{"year": str(r["fiscal_year"]), "revenue": r["operating_income"]/1e8, "profit": r["parent_holder_net_profit"]/1e8} for r in rows if r.get("operating_income") is not None and r.get("parent_holder_net_profit") is not None], "raw_items": rows, "missing_information": "利润表不提供 ROE；未取得资产负债表与现金流量表。财务趋势单位为亿元，利润为归母净利润。"}

    def valuation(args):
        path = "/api/a-share/valuations/snapshot"
        data = get(path, {"thscodes": args.symbol})
        row = data["item"][0]
        return {**base(args.symbol, path, data), "valuation": {"pe_ttm": row.get("pe_ttm"), "pb": row.get("pb_mrq"), "dividend_yield_percent": None}, "raw_items": data["item"], "missing_information": "PB 为 MRQ 口径；本接口不提供股息率或历史估值区间。"}

    registry = ToolRegistry()
    for name, model, handler in [("get_market_snapshot", StockArgs, market), ("get_financial_summary", FinancialArgs, financial), ("get_valuation_snapshot", StockArgs, valuation)]:
        registry.register(RegisteredTool(name, "Read Fuyao market data; no demo fallback.", model, handler, "FUYAO / MARKET DATA"))
    return registry
