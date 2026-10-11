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


class FixturePlanner:
    async def plan(self, goal: str, preferences: dict[str, Any]) -> PlanResult:
        symbol = resolve_symbol(goal)
        bank_risk = symbol in {"600036.SH", "000001.SZ"} and ("风险" in goal or "risk" in goal.lower())
        simulate_failure = "[simulate-failure]" in goal.lower()
        plan = ResearchPlan(
            research_goal=goal,
            tasks=[
                PlannedTask(title="Collect market snapshot", tool_name="get_market_snapshot", arguments={"symbol": symbol}, rationale="获取已识别标的的行情快照与历史日线。"),
                PlannedTask(title="银行利润表概览（风险指标待补充）" if bank_risk else "Review profitability", tool_name="get_financial_summary", arguments={"symbol": symbol, "fiscal_year": 2025, "simulate_failure": simulate_failure}, rationale="当前只读利润表；不良贷款率、拨备覆盖率、净息差与资本充足率尚未接入，风险研究覆盖有限。" if bank_risk else "查看已识别标的的最新可用年度财务指标。"),
                PlannedTask(title="Review valuation", tool_name="get_valuation_snapshot", arguments={"symbol": symbol}, rationale="查看已识别标的的估值指标。"),
            ],
        )
        return PlanResult(plan=plan, mode="fixture")

