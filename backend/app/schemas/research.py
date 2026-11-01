from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    task_key: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,50}$")
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    question: str = Field(default="", max_length=500)
    evidence_required: list[str] = Field(default_factory=list, max_length=10)
    completion_criteria: list[str] = Field(default_factory=list, max_length=10)


class ResearchPlan(BaseModel):
    research_type: Literal["profitability", "valuation", "risk", "comprehensive"] = "comprehensive"
    scope: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_goal: str = Field(min_length=1, max_length=1000)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_graph(self):
        import json
        keys = []
        signatures = set()
        for index, task in enumerate(self.tasks, 1):
            task.task_key = task.task_key or f"task_{index}"
            if task.task_key in keys:
                raise ValueError("Duplicate task key")
            signature = (task.tool_name, json.dumps(task.arguments, sort_keys=True, ensure_ascii=False))
            if signature in signatures:
                raise ValueError('Duplicate tool calls with identical arguments are forbidden')
            signatures.add(signature)
            keys.append(task.task_key)
        # Topological ordering makes execution and auditing unambiguous.
        visited = set()
        for task in self.tasks:
            if not set(task.depends_on) <= visited:
                raise ValueError("Dependencies must reference earlier tasks; cycles are forbidden")
            visited.add(task.task_key)
        return self


class CreateRunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=1000)
    thread_id: str | None = None
    thread_title: str | None = Field(default=None, max_length=200)
    preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator('preferences')
    @classmethod
    def bounded_preferences(cls, value):
        import json
        if len(json.dumps(value, ensure_ascii=False)) > 4000:
            raise ValueError('Research preferences exceed the allowed size')
        return value


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



class RetryFailedRequest(BaseModel):
    model_config = {"extra": "forbid"}
    plan_version: int = Field(ge=1)
    expected_updated_at: str = Field(min_length=1, max_length=100)


class SupplementRequest(RetryFailedRequest):
    pass
