from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


RunStatus = Literal[
    "PLANNING",
    "PENDING_APPROVAL",
    "APPROVED",
    "RUNNING",
    "COMPLETE",
    "PARTIAL",
    "FAILED",
    "REJECTED",
    "CANCELLED",
]


class PlannedTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]
    rationale: str = Field(min_length=1, max_length=500)


class ResearchPlan(BaseModel):
    research_type: Literal["profitability", "valuation", "risk", "comprehensive"] = "comprehensive"
    scope: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_goal: str = Field(min_length=1, max_length=1000)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=8)


class CreateRunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=1000)
    thread_id: str | None = None
    thread_title: str | None = Field(default=None, max_length=200)
    preferences: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    plan_version: int = Field(ge=1)
    allowed_tools: list[str] = Field(min_length=1)

    @field_validator("allowed_tools")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class RejectRequest(BaseModel):
    plan_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)

