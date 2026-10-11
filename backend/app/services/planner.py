import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.schemas.research import PlannedTask, ResearchPlan
from app.services.tools import ToolRegistry
from app.services.symbols import resolve_symbol


@dataclass
class PlanResult:
    plan: ResearchPlan
    mode: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class Planner(Protocol):
    async def plan(self, goal: str, preferences: dict[str, Any]) -> PlanResult: ...


class DeepSeekPlanner:
    def __init__(self, settings: Settings, registry: ToolRegistry) -> None:
        self.settings = settings
        self.registry = registry

    async def plan(self, goal: str, preferences: dict[str, Any]) -> PlanResult:
        if not self.settings.llm_configured:
            raise RuntimeError("DeepSeek planner is selected but its configuration is incomplete.")
        tool_specs = [
            {"name": item["name"], "parameters": item["parameters"]}
            for item in self.registry.schemas()
        ]
        instruction = (
            "Create a compact investment research plan using only the supplied fixture tools. "
            "Return one JSON object with research_goal and tasks. Each task requires title, "
            "tool_name, arguments, and rationale. Never invent a tool or metric. "
            f"Tools: {json.dumps(tool_specs, ensure_ascii=False)}. "
            f"Preferences: {json.dumps(preferences, ensure_ascii=False)}. Goal: {goal}"
        )
        url = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": "You are the planning component of a demo investment research agent."},
                {"role": "user", "content": instruction},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 900,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        return PlanResult(
            plan=ResearchPlan.model_validate(json.loads(content)),
            mode="deepseek",
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )


def classify_research_goal(goal: str) -> str:
    text = goal.lower()
    intents = set()
    if any(word in text for word in ("盈利", "利润", "profitability", "earnings")):
        intents.add("profitability")
    if any(word in text for word in ("估值", "valuation", "市盈率", "市净率")):
        intents.add("valuation")
    if any(word in text for word in ("风险", "risk")):
        intents.add("risk")
    return next(iter(intents)) if len(intents) == 1 else "comprehensive"


class FixturePlanner:
    async def plan(self, goal: str, preferences: dict[str, Any]) -> PlanResult:
        symbol = resolve_symbol(goal)
        focus = classify_research_goal(goal)
        bank_risk = symbol in {"600036.SH", "000001.SZ"} and ("风险" in goal or "risk" in goal.lower())
        simulate_failure = "[simulate-failure]" in goal.lower()
        market = PlannedTask(title="行情快照与历史走势", tool_name="get_market_snapshot", arguments={"symbol": symbol}, rationale="查看最近可用行情与前复权日线；价格波动不等于基本面风险。")
        financial = PlannedTask(title="银行利润表概览（风险指标待补充）" if bank_risk else "年度盈利与增长概览", tool_name="get_financial_summary", arguments={"symbol": symbol, "fiscal_year": 2025, "simulate_failure": simulate_failure}, rationale="当前只读利润表；不良贷款率、拨备覆盖率、净息差与资本充足率尚未接入，风险研究覆盖有限。" if bank_risk else "查看最新可用年度利润表与营收、归母利润趋势；不能替代现金流和资产负债分析。")
        valuation = PlannedTask(title="估值倍数核对", tool_name="get_valuation_snapshot", arguments={"symbol": symbol}, rationale="查看 PE(TTM) 与 PB(MRQ)；缺少历史和同业基准，不直接计算目标价。")
        tasks = {"profitability": [financial], "valuation": [valuation, financial], "risk": [market, financial, valuation], "comprehensive": [market, financial, valuation]}[focus]
        scope_names = {"get_market_snapshot": "最近行情与一年历史日线", "get_financial_summary": "最新可用五个年度利润表", "get_valuation_snapshot": "PE(TTM)、PB(MRQ) 估值快照"}
        limitations = ["未接入完整资产负债表与现金流量表，无法完整核验盈利质量。", "没有历史估值与同业比较，不提供公允价值或目标价。"]
        if focus == "risk" or bank_risk:
            limitations.append("银行不良贷款率、拨备覆盖率、净息差、资本与流动性指标尚未接入；仅提供风险线索。" if bank_risk else "风险事件、公告及行业数据尚未接入；仅提供风险线索，不能完成全面风险评估。")
        plan = ResearchPlan(research_goal=goal, research_type=focus, tasks=tasks, scope=[scope_names[t.tool_name] for t in tasks], limitations=limitations)
        return PlanResult(plan=plan, mode="fixture")
