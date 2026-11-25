"""Use the configured model to interpret feedback without granting tool access."""
import json
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field


class FeedbackInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=300)
    clarification: str | None = Field(default=None, max_length=300)
    focus: Literal["profitability", "valuation", "risk", "comprehensive"] | None = None
    fiscal_year: int | None = Field(default=None, ge=2020, le=2030)
    remove_tools: list[str] = Field(default_factory=list, max_length=8)
    require_tools: list[str] = Field(default_factory=list, max_length=8)


def _validated_interpretation(body, allowed, feedback):
    result = FeedbackInterpretation.model_validate_json(body["choices"][0]["message"]["content"])
    if not set(result.remove_tools + result.require_tools) <= allowed:
        raise ValueError("Model suggested a tool outside the registered scope.")
    if result.fiscal_year is not None and str(result.fiscal_year) not in feedback:
        raise ValueError("Model inferred a fiscal year the user did not specify.")
    return result


async def interpret_feedback(settings, registry, goal, plan, feedback):
    tools = [{"name": row["name"], "description": row["description"]}
             for row in registry.schemas() if row["name"] != "read_uploaded_annual_report"]
    instruction = (
        "你只解释用户对当前股票研究计划的修改意见，用中文输出一个符合 schema 的 JSON。"
        "不能执行工具、授权、变更证券或假定用户没有提供的年份。用户要求更换证券时，请澄清并提示直接编辑研究要求。"
        "focus 只在意见明确要求改变研究重点时填写。关心利润现金流支撑属于 profitability；"
        "如果用户要求保留原计划、顺便补充或追加一项资料，focus 留空，只把明确请求新增的工具放入 require_tools，保留当前步骤。"
        "扶摇 get_fuyao_cash_flow 和 get_fuyao_balance_sheet 可以直接追加；已导入资料的工具仅在有对应资料时可用。"
        "如果只关心利润与现金流，明确移除行情、估值以及用户不希望查的步骤，并要求保留利润表和现金流。"
        "最近一年使用最新可用年度，只有明确指定 4 位财年才填 fiscal_year。"
        "remove_tools/require_tools 仅能使用提供的工具名。"
        "用户取消尚未排入的步骤时仍可列入 remove_tools，系统将说明无需取消。"
        "意见有歧义、依赖缺失或无法支持时，clarification 填一个具体问题。"
        "summary 简述你理解的需求，不声称已执行或已获得数据。"
    )
    allowed = {row["name"] for row in tools}
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": json.dumps(
                {"goal": goal, "plan": plan, "feedback": feedback, "tools": tools,
                 "schema": FeedbackInterpretation.model_json_schema()}, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"}, "temperature": 0,
    }
    prompt_tokens = completion_tokens = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(28, connect=8)) as client:
        for attempt in range(2):
            response = await client.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key.get_secret_value()}"},
                json=payload,
            )
            response.raise_for_status()
            try:
                body = response.json()
                usage = body.get("usage") or {}
                prompt_tokens += int(usage.get("prompt_tokens") or 0)
                completion_tokens += int(usage.get("completion_tokens") or 0)
                result = _validated_interpretation(body, allowed, feedback)
            except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                if attempt == 1:
                    raise ValueError("Model response remains invalid after correction.") from None
                payload["messages"].append({"role": "user", "content": "上次返回没有通过校验。请仅返回符合 schema 的 JSON，工具名必须来自列表，未明确给出财年时 fiscal_year 必须为空。"})
            else:
                return result, prompt_tokens, completion_tokens
