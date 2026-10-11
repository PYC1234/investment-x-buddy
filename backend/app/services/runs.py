import json
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.research import ApprovalRequest, CreateRunRequest, RejectRequest
from app.services.planner import DeepSeekPlanner, FixturePlanner, Planner
from app.services.store import SQLiteStore
from app.services.tools import ToolExecutionError, ToolRegistry, build_tool_registry


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunService:
    def __init__(self, settings: Settings, store: SQLiteStore, registry: ToolRegistry, planner: Planner) -> None:
        self.settings = settings
        self.store = store
        self.registry = registry
        self.planner = planner

    def _event(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        self.store.execute(
            "INSERT INTO events(run_id,event_type,data_json,created_at) VALUES(?,?,?,?)",
            (run_id, event_type, json.dumps(data, ensure_ascii=False), now_iso()),
        )

    def _run_or_404(self, run_id: str) -> dict[str, Any]:
        run = self.store.fetch_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if not run:
            raise AppError(status_code=404, code="run_not_found", message="Run not found.")
        return run

    async def create_run(self, request: CreateRunRequest) -> dict[str, Any]:
        timestamp = now_iso()
        thread_id = request.thread_id or str(uuid4())
        if request.thread_id:
            if not self.store.fetch_one("SELECT * FROM threads WHERE id=?", (thread_id,)):
                raise AppError(status_code=404, code="thread_not_found", message="Thread not found.")
        else:
            self.store.execute(
                "INSERT INTO threads(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                (thread_id, request.thread_title or request.goal[:100], timestamp, timestamp),
            )
        if request.preferences:
            self.save_memory(thread_id, "research_preferences", request.preferences)

        run_id = str(uuid4())
        self.store.execute(
            """INSERT INTO runs(id,thread_id,goal,status,plan_version,planner_mode,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (run_id, thread_id, request.goal, "PLANNING", 1, self.settings.planner_mode, timestamp, timestamp),
        )
        self._event(run_id, "run.created", {"status": "PLANNING"})
        preferences = self.get_memory(thread_id).get("research_preferences", {})
        try:
            result = await self.planner.plan(request.goal, preferences)
            for task in result.plan.tasks:
                self.registry.validate(task.tool_name, task.arguments)
        except (ValueError, json.JSONDecodeError) as exc:
            self.store.execute("UPDATE runs SET status='FAILED',error=?,updated_at=? WHERE id=?", (str(exc), now_iso(), run_id))
            self._event(run_id, "plan.invalid", {"error": "Planner returned an invalid or unauthorized plan."})
            raise AppError(status_code=422, code="invalid_plan", message="Planner returned an invalid or unauthorized plan.") from exc
        except (httpx.HTTPError, RuntimeError, KeyError) as exc:
            self.store.execute("UPDATE runs SET status='FAILED',error=?,updated_at=? WHERE id=?", (type(exc).__name__, now_iso(), run_id))
            self._event(run_id, "plan.failed", {"error_type": type(exc).__name__})
            raise AppError(status_code=502, code="planner_failed", message="Planner request failed.") from exc

        estimated_cost = self._estimate_cost(result.prompt_tokens, result.completion_tokens)
        plan_data = result.plan.model_dump()
        self.store.execute(
            """UPDATE runs SET status='PENDING_APPROVAL',planner_mode=?,plan_json=?,prompt_tokens=?,
               completion_tokens=?,estimated_cost_usd=?,updated_at=? WHERE id=?""",
            (result.mode, json.dumps(plan_data, ensure_ascii=False), result.prompt_tokens, result.completion_tokens, estimated_cost, now_iso(), run_id),
        )
        for position, task in enumerate(result.plan.tasks, start=1):
            self.store.execute(
                """INSERT INTO tasks(id,run_id,plan_version,position,title,tool_name,arguments_json,rationale,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid4()), run_id, 1, position, task.title, task.tool_name, json.dumps(task.arguments, ensure_ascii=False), task.rationale, "PENDING", timestamp, timestamp),
            )
        self._event(run_id, "plan.generated", {"plan_version": 1, "planner_mode": result.mode, "tool_names": [task.tool_name for task in result.plan.tasks]})
        self._save_checkpoint(run_id, "PENDING_APPROVAL")
        return self.get_run(run_id)

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float | None:
        if self.settings.deepseek_input_cost_per_1m is None or self.settings.deepseek_output_cost_per_1m is None:
            return None
        return round((prompt_tokens * self.settings.deepseek_input_cost_per_1m + completion_tokens * self.settings.deepseek_output_cost_per_1m) / 1_000_000, 8)

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        run["tasks"] = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))
        prompt_tokens = run.pop("prompt_tokens")
        completion_tokens = run.pop("completion_tokens")
        run["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost_usd": run.pop("estimated_cost_usd"),
            "cost_status": "configured" if self.settings.deepseek_input_cost_per_1m is not None and self.settings.deepseek_output_cost_per_1m is not None else "NOT_CONFIGURED",
        }
        return run

    async def approve(self, run_id: str, approval: ApprovalRequest) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] != "PENDING_APPROVAL":
            raise AppError(status_code=409, code="approval_not_allowed", message="Run is not waiting for approval.")
        if approval.plan_version != run["plan_version"]:
            raise AppError(status_code=409, code="plan_version_mismatch", message="Approval does not match the current plan version.")
        requested = set(approval.allowed_tools)
        if not requested.issubset(self.registry.names()):
            raise AppError(status_code=400, code="unauthorized_tool", message="Approval contains an unregistered tool.")
        tasks = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=?", (run_id,))
        required = {task["tool_name"] for task in tasks}
        if not required.issubset(requested):
            raise AppError(status_code=400, code="approval_scope_incomplete", message="Approval tool scope does not cover the plan.")
        approval_data = {"plan_version": approval.plan_version, "allowed_tools": sorted(requested), "approved_at": now_iso()}
        self.store.execute("UPDATE runs SET status='APPROVED',approval_json=?,updated_at=? WHERE id=?", (json.dumps(approval_data), now_iso(), run_id))
        self._event(run_id, "plan.approved", approval_data)
        return await self.execute(run_id)

    def reject(self, run_id: str, rejection: RejectRequest) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] != "PENDING_APPROVAL" or rejection.plan_version != run["plan_version"]:
            raise AppError(status_code=409, code="rejection_not_allowed", message="Run or plan version cannot be rejected.")
        self.store.execute("UPDATE runs SET status='REJECTED',error=?,updated_at=?,completed_at=? WHERE id=?", (rejection.reason, now_iso(), now_iso(), run_id))
        self._event(run_id, "plan.rejected", {"plan_version": rejection.plan_version, "reason": rejection.reason})
        self._save_checkpoint(run_id, "REJECTED")
        return self.get_run(run_id)

    async def execute(self, run_id: str) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        approval = run.get("approval")
        if not approval or approval.get("plan_version") != run["plan_version"]:
            raise AppError(status_code=409, code="approval_required", message="A matching plan approval is required before execution.")
        if run["status"] in {"REJECTED", "CANCELLED", "PENDING_APPROVAL", "PLANNING"}:
            raise AppError(status_code=409, code="execution_not_allowed", message="Run cannot execute in its current state.")
        self.store.execute("UPDATE runs SET status='RUNNING',started_at=COALESCE(started_at,?),updated_at=? WHERE id=?", (now_iso(), now_iso(), run_id))
        self._event(run_id, "execution.started", {"resumed": run["status"] in {"PARTIAL", "FAILED", "RUNNING"}})
        started = time.monotonic()
        rounds = 0
        calls = len(self.store.fetch_all("SELECT id FROM tool_calls WHERE run_id=?", (run_id,)))
        stop_reason: str | None = None
        tasks = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))
        for task in tasks:
            if task["status"] == "COMPLETED" or task["status"] == "FAILED":
                continue
            latest = self._run_or_404(run_id)
            if latest["status"] == "CANCELLED":
                stop_reason = "cancelled"
                break
            if rounds >= self.settings.max_execution_rounds:
                stop_reason = "max_execution_rounds"
                break
            if calls >= self.settings.max_tool_calls:
                stop_reason = "max_tool_calls"
                break
            if time.monotonic() - started >= self.settings.run_timeout_seconds:
                stop_reason = "run_timeout"
                break
            if task["tool_name"] not in approval["allowed_tools"] or task["tool_name"] not in self.registry.names():
                self._fail_task(task, "Tool is outside the approved registry scope.")
                continue
            try:
                validated = self.registry.validate(task["tool_name"], task["arguments"])
            except ValueError as exc:
                self._fail_task(task, str(exc))
                continue
            rounds += 1
            max_attempts = self.settings.max_tool_retries + 1
            while task["attempts"] < max_attempts and calls < self.settings.max_tool_calls:
                attempt = task["attempts"] + 1
                task["attempts"] = attempt
                calls += 1
                self.store.execute("UPDATE tasks SET status='RUNNING',attempts=?,updated_at=? WHERE id=?", (attempt, now_iso(), task["id"]))
                call_started = time.perf_counter()
                try:
                    result, _ = self.registry.execute(task["tool_name"], validated)
                    duration = (time.perf_counter() - call_started) * 1000
                    evidence_id = f"EVD-{uuid4().hex[:12].upper()}"
                    self.store.execute("INSERT INTO evidence(id,run_id,task_id,tool_name,title,data_json,is_demo,created_at) VALUES(?,?,?,?,?,?,?,?)", (evidence_id, run_id, task["id"], task["tool_name"], task["title"], json.dumps(result, ensure_ascii=False), int(result.get("is_demo", True)), now_iso()))
                    self._record_tool_call(run_id, task, attempt, "SUCCESS", duration, result, None)
                    self.store.execute("UPDATE tasks SET status='COMPLETED',evidence_id=?,error=NULL,updated_at=? WHERE id=?", (evidence_id, now_iso(), task["id"]))
                    self._event(run_id, "tool.completed", {"task_id": task["id"], "tool_name": task["tool_name"], "evidence_id": evidence_id, "duration_ms": round(duration, 3)})
                    break
                except ToolExecutionError as exc:
                    duration = (time.perf_counter() - call_started) * 1000
                    self._record_tool_call(run_id, task, attempt, "ERROR", duration, None, str(exc))
                    self._event(run_id, "tool.failed", {"task_id": task["id"], "tool_name": task["tool_name"], "attempt": attempt, "error": str(exc)})
                    if attempt >= max_attempts:
                        self._fail_task(task, str(exc))
            self._save_checkpoint(run_id, "RUNNING")

        current_tasks = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))
        failed = [task for task in current_tasks if task["status"] != "COMPLETED"]
        final_status = "PARTIAL" if failed or stop_reason else "COMPLETE"
        report = self._build_report(run_id, final_status, stop_reason)
        self.store.execute("UPDATE runs SET status=?,report_json=?,error=?,updated_at=?,completed_at=? WHERE id=?", (final_status, json.dumps(report, ensure_ascii=False), stop_reason, now_iso(), now_iso(), run_id))
        self._event(run_id, "run.completed", {"status": final_status, "stop_reason": stop_reason})
        self._save_checkpoint(run_id, final_status)
        return self.get_run(run_id)

    def _record_tool_call(self, run_id: str, task: dict[str, Any], attempt: int, status: str, duration: float, result: dict[str, Any] | None, error: str | None) -> None:
        self.store.execute("INSERT INTO tool_calls(id,run_id,task_id,tool_name,attempt,status,duration_ms,result_json,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(uuid4()), run_id, task["id"], task["tool_name"], attempt, status, duration, json.dumps(result, ensure_ascii=False) if result else None, error, now_iso()))

    def _fail_task(self, task: dict[str, Any], error: str) -> None:
        self.store.execute("UPDATE tasks SET status='FAILED',error=?,updated_at=? WHERE id=?", (error, now_iso(), task["id"]))

    def _build_report(self, run_id: str, status: str, stop_reason: str | None) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        tasks = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))
        evidence = self.store.fetch_all("SELECT * FROM evidence WHERE run_id=? ORDER BY created_at", (run_id,))
        if any(not item["is_demo"] for item in evidence) or any(tool["data_source"] == "FUYAO / MARKET DATA" for tool in self.registry.schemas()):
            findings = []
            missing = [task["title"] + ": " + str(task.get("error") or "未完成") for task in tasks if task["status"] != "COMPLETED"]
            def number(value):
                return "未提供" if value is None else f"{value:,.2f}"
            for item in evidence:
                data = item["data"]
                if item["is_demo"]:
                    statement = "DEMO DATA：此条为演示证据，不可用于真实结论。"
                elif "snapshot" in data:
                    row = data["snapshot"]
                    statement = f"扶摇行情快照：价格 {number(row.get('price_cny'))} 元，涨跌幅 {number(row.get('change_percent'))}%。取得 {len(data.get('prices', []))} 条前复权日线。快照时间戳（毫秒）{data.get('timestamp_ms')}；非交易时间为最近可用数据。"
                elif "valuation" in data:
                    row = data["valuation"]
                    statement = f"估值：PE(TTM) {number(row.get('pe_ttm'))} 倍，PB(MRQ) {number(row.get('pb'))} 倍。倍数反映市场定价，缺少同业和历史区间，不能单凭倍数认定低估或高估。"
                else:
                    rows = data.get("financial_history", [])
                    latest = rows[-1] if rows else {}
                    statement = f"盈利：{latest.get('year', '最近年度')} 年营业收入 {number(latest.get('revenue'))} 亿元，归母净利润 {number(latest.get('profit'))} 亿元。"
                    if len(rows) > 1 and rows[-2].get('revenue'):
                        growth = (latest['revenue'] / rows[-2]['revenue'] - 1) * 100
                        statement += f"营业收入较上一可用年度变化 {growth:.2f}%；需结合现金回款验证盈利质量。"
                findings.append({"task": item["title"], "statement": statement, "evidence_ids": [item["id"]]})
                if data.get("missing_information"):
                    missing.append(data["missing_information"])
            missing.extend(["数据来自扶摇接口，尚未与交易所原始公告交叉核验；行情时间以证据时间戳为准。", "缺少历史估值区间、同业比较、现金流和负债数据，无法可靠计算公允价值或目标价。", "风险待验证：需求与渠道回款走弱可能影响利润；利率或风险偏好变化可能压缩估值。", "COMPLETE 表示任务完成，不表示投资结论已充分验证。"])
            if stop_reason:
                missing.append(stop_reason)
            return {"title": f"估值与风险研究：{run['goal']}", "status": status, "data_notice": "FUYAO / MARKET DATA · 真实接口数据；非交易时段为最近可用行情。", "executive_summary": f"完成 {len(evidence)}/{len(tasks)} 项证据任务。依据行情、年度利润表和估值快照整理研究；报告为证据驱动的规则分析，未调用收费报告模型。", "findings": findings, "missing_information": missing, "evidence_ids": [item["id"] for item in evidence]}
        by_task = {item["task_id"]: item for item in evidence}
        findings = []
        missing = []
        for task in tasks:
            item = by_task.get(task["id"])
            if item:
                data = item["data"]
                available = data.get("available", True)
                snapshot = data.get("snapshot")
                valuation = data.get("valuation")
                financials = data.get("financials")
                statement = "当前证据未包含可用指标；不能据此形成估值结论。"
                if available and snapshot:
                    statement = f"行情快照（DEMO DATA）：示例价格为 {snapshot['price_cny']:g} 元，单日变动 {snapshot.get('change_percent', 0):g}%，时间标记为 {snapshot.get('as_of', '未知')}。单日变动不能代表长期趋势，且该价格不是实时行情。"
                elif available and valuation:
                    statement = f"估值观察（DEMO DATA）：PE(TTM) 为 {valuation['pe_ttm']:g} 倍、PB 为 {valuation['pb']:g} 倍、股息率为 {valuation['dividend_yield_percent']:g}%。这些倍数需结合盈利持续性、历史区间和同业比较判断；现有证据不足以认定低估或高估，也不能给出目标价。"
                elif available and financials:
                    statement = f"盈利能力（DEMO DATA，{data.get('fiscal_year')} 年）：ROE 为 {financials['roe_percent']:g}%，净利率为 {financials['net_margin_percent']:g}%，营收增速为 {financials['revenue_growth_percent']:g}%。样本呈现较强盈利能力，但单年指标无法证明增长可持续，需补充现金流与多年财报。"
                findings.append({"task": task["title"], "statement": statement, "evidence_ids": [item["id"]]})
                if not available:
                    missing.append(data.get("missing_information") or f"Missing data for {task['title']}.")
            else:
                missing.append(task.get("error") or f"No evidence produced for {task['title']}.")
        if stop_reason:
            missing.append(f"Execution stopped by rule: {stop_reason}.")
        valid = [item for item in evidence if item["data"].get("available")]
        if valid:
            findings.append({"task": "风险与待验证假设", "statement": "研究风险清单（待验证，并非已发生事实）：若需求、产品价格或渠道回款走弱，盈利增长可能低于预期；若市场要求的回报率上升，估值倍数可能收缩。现有 Fixture 指标无法判断这些风险的概率或幅度，需用真实公告和行业数据核实。", "evidence_ids": [item["id"] for item in valid]})
        missing.extend([
            "所有金融指标均为人工构造的 DEMO DATA；尚未核验实时行情、交易所公告及经审计财报。",
            "缺少历史估值区间、同业比较、现金流、负债及渠道数据，无法形成真实公允价值或目标价。",
            "需求变化、竞争、政策和治理风险尚未用独立来源验证；风险清单仅为下一步研究问题。",
            "COMPLETE 仅表示计划任务执行完成，不表示投资结论已得到充分验证。",
        ])
        summary = f"已完成 {sum(task['status'] == 'COMPLETED' for task in tasks)}/{len(tasks)} 项证据任务，取得 {len(valid)} 条可用演示证据。"
        summary += "本报告从估值倍数、盈利能力与风险假设整理研究框架；由于数据为 Fixture 且缺少比较基准，结论是需要补充验证，不能据此给出买卖判断。"
        return {"title": f"估值与风险研究：{run['goal']}", "status": status, "data_notice": "DEMO DATA · 所有金融数值均为演示样本，不是真实行情或投资建议。", "executive_summary": summary, "findings": findings, "missing_information": missing, "evidence_ids": [item["id"] for item in evidence]}


    def _save_checkpoint(self, run_id: str, status: str) -> None:
        tasks = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))
        evidence = self.store.fetch_all("SELECT * FROM evidence WHERE run_id=? ORDER BY created_at", (run_id,))
        full_context = json.dumps({"status": status, "tasks": tasks, "evidence": evidence}, ensure_ascii=False, indent=2)
        summary_data = {"status": status, "completed_task_ids": [task["id"] for task in tasks if task["status"] == "COMPLETED"], "failed_task_ids": [task["id"] for task in tasks if task["status"] == "FAILED"], "evidence_ids": [item["id"] for item in evidence]}
        summary = json.dumps(summary_data, ensure_ascii=False, separators=(",", ":"))
        existing = self.store.fetch_one("SELECT COALESCE(MAX(sequence),0) AS sequence FROM checkpoints WHERE run_id=?", (run_id,))
        sequence = int(existing["sequence"]) + 1
        self.store.execute("INSERT INTO checkpoints(id,run_id,sequence,state_json,context_summary,before_chars,after_chars,created_at) VALUES(?,?,?,?,?,?,?,?)", (str(uuid4()), run_id, sequence, json.dumps(summary_data), summary, len(full_context), len(summary), now_iso()))
        self._event(run_id, "checkpoint.saved", {"sequence": sequence, "before_chars": len(full_context), "after_chars": len(summary)})

    async def resume(self, run_id: str) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] == "COMPLETE":
            return self.get_run(run_id)
        if run["status"] not in {"APPROVED", "RUNNING", "PARTIAL", "FAILED"}:
            raise AppError(status_code=409, code="resume_not_allowed", message="Run cannot be resumed in its current state.")
        self.store.execute("UPDATE tasks SET status='PENDING',updated_at=? WHERE run_id=? AND status='RUNNING'", (now_iso(), run_id))
        self._event(run_id, "run.resumed", {"checkpoint_loaded": bool(self.get_checkpoints(run_id))})
        return await self.execute(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] in {"COMPLETE", "REJECTED", "CANCELLED"}:
            raise AppError(status_code=409, code="cancel_not_allowed", message="Run is already terminal.")
        self.store.execute("UPDATE runs SET status='CANCELLED',updated_at=?,completed_at=? WHERE id=?", (now_iso(), now_iso(), run_id))
        self._event(run_id, "run.cancelled", {})
        self._save_checkpoint(run_id, "CANCELLED")
        return self.get_run(run_id)

    def save_memory(self, thread_id: str, key: str, value: dict[str, Any]) -> None:
        self.store.execute("""INSERT INTO memories(id,thread_id,memory_key,value_json,updated_at) VALUES(?,?,?,?,?)
            ON CONFLICT(thread_id,memory_key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""", (str(uuid4()), thread_id, key, json.dumps(value, ensure_ascii=False), now_iso()))

    def get_memory(self, thread_id: str) -> dict[str, Any]:
        return {item["memory_key"]: item["value"] for item in self.store.fetch_all("SELECT * FROM memories WHERE thread_id=?", (thread_id,))}

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        self._run_or_404(run_id)
        return self.store.fetch_all("SELECT id,event_type,data_json,created_at FROM events WHERE run_id=? ORDER BY id", (run_id,))

    def get_evidence(self, run_id: str) -> list[dict[str, Any]]:
        self._run_or_404(run_id)
        return self.store.fetch_all("SELECT * FROM evidence WHERE run_id=? ORDER BY created_at", (run_id,))

    def get_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        self._run_or_404(run_id)
        return self.store.fetch_all("SELECT * FROM checkpoints WHERE run_id=? ORDER BY sequence", (run_id,))

    def get_tool_calls(self, run_id: str) -> list[dict[str, Any]]:
        self._run_or_404(run_id)
        return self.store.fetch_all(
            "SELECT * FROM tool_calls WHERE run_id=? ORDER BY created_at", (run_id,)
        )

    def get_report(self, run_id: str) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if not run.get("report"):
            raise AppError(status_code=409, code="report_not_ready", message="Report is not available yet.")
        return run["report"]

    def list_threads(self) -> list[dict[str, Any]]:
        threads = self.store.fetch_all("SELECT * FROM threads ORDER BY updated_at DESC")
        for thread in threads:
            thread["memory"] = self.get_memory(thread["id"])
            thread["runs"] = self.store.fetch_all("SELECT id,goal,status,planner_mode,created_at,updated_at FROM runs WHERE thread_id=? ORDER BY created_at DESC", (thread["id"],))
        return threads

    def list_tools(self) -> list[dict[str, Any]]:
        return self.registry.schemas()


@lru_cache
def get_run_service() -> RunService:
    settings = get_settings()
    from app.services.fuyao import build_fuyao_registry
    registry = build_fuyao_registry(settings.fuyao_api_key) if settings.finance_provider_configured else build_tool_registry()
    planner: Planner = FixturePlanner() if settings.planner_mode == "fixture" else DeepSeekPlanner(settings, registry)
    return RunService(settings, SQLiteStore(settings.sqlite_path), registry, planner)

