import json
import re
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.research import ApprovalRequest, CreateRunRequest, RejectRequest, RetryFailedRequest, ResearchPlan, RevisePlanRequest
from app.services.planner import DeepSeekPlanner, FixturePlanner, Planner
from app.services.store import SQLiteStore
from app.services.evidence_quality import assess_evidence
from app.services.symbols import SymbolResolutionError, resolve_symbol
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

    async def create_run(self, request: CreateRunRequest, owner_id: str | None = None) -> dict[str, Any]:
        timestamp = now_iso()
        thread_id = request.thread_id or str(uuid4())
        run_id = str(uuid4())
        with self.store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            if owner_id:
                active = con.execute("SELECT COUNT(*) FROM runs r JOIN threads t ON t.id=r.thread_id WHERE t.owner_id=? AND r.status IN ('PLANNING','PENDING_APPROVAL','APPROVED','RUNNING')", (owner_id,)).fetchone()[0]
                if active >= self.settings.max_active_runs_per_user:
                    raise AppError(status_code=429, code='active_run_limit', message='待确认或执行中的研究过多，请先完成、拒绝或停止已有研究。')
            if request.thread_id:
                row = con.execute('SELECT owner_id FROM threads WHERE id=?', (thread_id,)).fetchone()
                if row is None or (owner_id is not None and row['owner_id'] != owner_id):
                    raise AppError(status_code=404, code='thread_not_found', message='Thread not found.')
            else:
                con.execute('INSERT INTO threads(id,title,created_at,updated_at,owner_id) VALUES(?,?,?,?,?)',
                    (thread_id, request.thread_title or request.goal[:100], timestamp, timestamp, owner_id))
            con.execute(
            """INSERT INTO runs(id,thread_id,goal,status,plan_version,planner_mode,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (run_id, thread_id, request.goal, "PLANNING", 1, self.settings.planner_mode, timestamp, timestamp),
            )
        if request.preferences:
            self.save_memory(thread_id, "research_preferences", request.preferences)
        self._event(run_id, "run.created", {"status": "PLANNING"})
        preferences = self.get_memory(thread_id).get("research_preferences", {})
        from app.services.annual_update import AnnualScopeError

        try:
            result = await self._build_plan(request, preferences)
        except (SymbolResolutionError, AnnualScopeError) as exc:
            self.store.execute("UPDATE runs SET status='FAILED',error=?,updated_at=? WHERE id=?", (str(exc), now_iso(), run_id))
            self._event(run_id, "plan.invalid", {"error": str(exc)})
            raise AppError(status_code=422, code="invalid_annual_scope" if isinstance(exc, AnnualScopeError) else "invalid_symbol", message=str(exc)) from exc
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
                """INSERT INTO tasks(id,run_id,plan_version,position,title,tool_name,arguments_json,rationale,status,created_at,updated_at,task_key,depends_on_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid4()), run_id, 1, position, task.title, task.tool_name, json.dumps(task.arguments, ensure_ascii=False), task.rationale, "PENDING", timestamp, timestamp, task.task_key, json.dumps(task.depends_on)),
            )
        self._event(run_id, "plan.generated", {"plan_version": 1, "planner_mode": result.mode, "tool_names": [task.tool_name for task in result.plan.tasks]})
        self._save_checkpoint(run_id, "PENDING_APPROVAL")
        return self.get_run(run_id)

    async def _build_plan(self, request: CreateRunRequest, preferences: dict[str, Any]):
        from app.services.annual_update import annual_update_year, build_annual_update
        from app.schemas.research import PlannedTask
        from app.services.planner import PlanResult
        from app.services.official_filings import OFFICIAL_FILING_TOOL

        year = request.annual_scope.fiscal_year if request.annual_scope else annual_update_year(request.goal)
        if year is None:
            result = await self.planner.plan(request.goal, preferences)
            if result.plan.research_type == "profitability":
                from app.services.fuyao import FUYAO_STATEMENTS
                from app.services.research_sources import SUPPLEMENT_TOOLS
                planned = {task.tool_name for task in result.plan.tasks}
                labels = {key: label for key, label in SUPPLEMENT_TOOLS.values()}
                for name, (_, dataset, _) in FUYAO_STATEMENTS.items():
                    if name in planned or name not in self.registry.names() or len(result.plan.tasks) >= 8:
                        continue
                    label = labels[dataset]
                    result.plan.tasks.append(PlannedTask(
                        task_key=f"fuyao_{dataset}", tool_name=name, title=f"年度合并{label}",
                        arguments={"symbol": resolve_symbol(request.goal)}, rationale=f"从扶摇获取{label}用于盈利质量核验。",
                    ))
                    result.plan.scope.append(f"扶摇年度合并{label}")
                if set(FUYAO_STATEMENTS) <= {task.tool_name for task in result.plan.tasks}:
                    result.plan.limitations = ["报表覆盖和年度可比性以工具结果为准；尚未与交易所原文交叉核验。"]
        else:
            plan = build_annual_update(request.goal, request.annual_scope.symbol if request.annual_scope else resolve_symbol(request.goal), year,
                                       self.settings.research_data_dir)
            result = PlanResult(plan, "annual_update")
        if result.plan.research_type == "profitability" and OFFICIAL_FILING_TOOL in self.registry.names():
            financial = next((task for task in result.plan.tasks if task.tool_name == "get_financial_summary"), None)
            planned = {task.tool_name for task in result.plan.tasks}
            if (financial and OFFICIAL_FILING_TOOL not in planned
                    and "search_company_filings" not in planned and len(result.plan.tasks) < 8):
                result.plan.tasks.append(PlannedTask(
                    task_key="official_annual_filing", title="查找同财年官方年报",
                    tool_name=OFFICIAL_FILING_TOOL, arguments={"symbol": financial.arguments["symbol"], "fiscal_year": year},
                    depends_on=[financial.task_key] if year is None and financial.task_key else [],
                    rationale="通过巨潮资讯检索同标的年报，引用支持盈利变化的原文与页码。",
                ))
                result.plan.scope.append("通过巨潮资讯定位官方年报")
                if year is not None:
                    result.plan.limitations = [
                        "年报扫描覆盖有限，未找到对应管理层解释时保留缺口。"
                    ]
        for task in result.plan.tasks:
            if task.tool_name == "read_uploaded_annual_report":
                raise ValueError("Uploaded PDF evidence requires an owned run and supplemental approval")
            self.registry.validate(task.tool_name, task.arguments)
        symbol = request.annual_scope.symbol if request.annual_scope else resolve_symbol(request.goal)
        for task in result.plan.tasks:
            if task.arguments.get('symbol') != symbol:
                raise ValueError('Plan stock does not match the confirmed research goal')
        return result

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float | None:
        if self.settings.deepseek_input_cost_per_1m is None or self.settings.deepseek_output_cost_per_1m is None:
            return None
        return round((prompt_tokens * self.settings.deepseek_input_cost_per_1m + completion_tokens * self.settings.deepseek_output_cost_per_1m) / 1_000_000, 8)

    async def revise_plan(self, run_id: str, revision: RevisePlanRequest) -> dict[str, Any]:
        from app.services.annual_update import AnnualScopeError
        from app.services.planner import PlanResult

        run = self._run_or_404(run_id)
        stale = AppError(status_code=409, code="plan_revision_conflict", message="计划已更新或已开始执行，请刷新后再操作。")
        if (run["status"] != "PENDING_APPROVAL" or run.get("approval")
                or revision.plan_version != run["plan_version"] or revision.expected_updated_at != run["updated_at"]):
            raise stale
        goal = revision.goal.strip()
        excluded = set(revision.excluded_tools)
        feedback = revision.feedback.strip()
        if feedback:
            try:
                goal, removed = self._apply_plan_feedback(goal, feedback, run["plan"]["tasks"])
            except SymbolResolutionError as exc:
                raise AppError(status_code=422, code="invalid_revised_scope", message=str(exc)) from exc
            excluded.update(removed)
        if not excluded and goal == run["goal"]:
            raise AppError(status_code=422, code="plan_unchanged", message="请修改研究要求或取消不需要的工具。")
        if not excluded <= {task["tool_name"] for task in run["plan"]["tasks"]}:
            raise AppError(status_code=422, code="unknown_excluded_tool", message="只能取消当前计划里的工具。")
        try:
            if goal == run["goal"]:
                result = PlanResult(ResearchPlan.model_validate(run["plan"]), run["planner_mode"])
            else:
                preferences = self.get_memory(run["thread_id"]).get("research_preferences", {})
                result = await self._build_plan(CreateRunRequest(goal=goal), preferences)
            if excluded:
                tasks = [task for task in result.plan.tasks if task.tool_name not in excluded]
                if not tasks:
                    raise ValueError("请至少保留一个工具。")
                keys = {task.task_key for task in tasks}
                if any(set(task.depends_on) - keys for task in tasks):
                    raise ValueError("保留的任务依赖已取消的工具。请保留前置工具或同时取消依赖项。")
                if result.mode == "annual_update" and tasks[0].tool_name != "get_financial_summary":
                    raise ValueError("年度财报更新需要保留利润表工具，以确认财年。")
                result.plan = ResearchPlan.model_validate({
                    **result.plan.model_dump(), "tasks": [task.model_dump() for task in tasks],
                    "scope": [task.title for task in tasks],
                })
        except (SymbolResolutionError, AnnualScopeError) as exc:
            raise AppError(status_code=422, code="invalid_revised_scope", message=str(exc)) from exc
        except ValueError as exc:
            message = str(exc) if str(exc).startswith(("请", "保留", "年度")) else "无法生成有效计划。请明确标的、研究重点和财年。"
            raise AppError(status_code=422, code="invalid_revised_plan", message=message) from exc
        except (httpx.HTTPError, RuntimeError, KeyError) as exc:
            raise AppError(status_code=502, code="planner_failed", message="生成新版计划失败，原计划仍可使用。") from exc

        version = revision.plan_version + 1
        timestamp = now_iso()
        prompt_tokens = run["prompt_tokens"] + result.prompt_tokens
        completion_tokens = run["completion_tokens"] + result.completion_tokens
        plan_data = result.plan.model_dump()
        with self.store.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                """UPDATE runs SET goal=?, planner_mode=?, plan_version=?, plan_json=?, approval_json=NULL,
                   prompt_tokens=?, completion_tokens=?, estimated_cost_usd=?, updated_at=?
                   WHERE id=? AND status='PENDING_APPROVAL' AND approval_json IS NULL AND plan_version=? AND updated_at=?""",
                (goal, result.mode, version, json.dumps(plan_data, ensure_ascii=False), prompt_tokens,
                 completion_tokens, self._estimate_cost(prompt_tokens, completion_tokens),
                 timestamp, run_id, revision.plan_version, revision.expected_updated_at),
            )
            if changed.rowcount != 1:
                raise stale
            con.execute("DELETE FROM tasks WHERE run_id=? AND plan_version=?", (run_id, revision.plan_version))
            con.executemany(
                """INSERT INTO tasks(id,run_id,plan_version,position,title,tool_name,arguments_json,rationale,
                   status,created_at,updated_at,task_key,depends_on_json) VALUES(?,?,?,?,?,?,?,?,'PENDING',?,?,?,?)""",
                [(str(uuid4()), run_id, version, position, task.title, task.tool_name,
                  json.dumps(task.arguments, ensure_ascii=False), task.rationale, timestamp, timestamp,
                  task.task_key, json.dumps(task.depends_on)) for position, task in enumerate(result.plan.tasks, 1)],
            )
            con.execute("UPDATE threads SET updated_at=? WHERE id=?", (timestamp, run["thread_id"]))
            con.execute("INSERT INTO events(run_id,event_type,data_json,created_at) VALUES(?,?,?,?)",
                        (run_id, "plan.revised", json.dumps({
                            "previous_version": revision.plan_version, "plan_version": version,
                            "excluded_tools": sorted(excluded), "tool_names": [task.tool_name for task in result.plan.tasks],
                        }), timestamp))
        self._save_checkpoint(run_id, "PENDING_APPROVAL")
        return self.get_run(run_id)

    @staticmethod
    def _apply_plan_feedback(goal, feedback, tasks):
        removed = set()
        aliases = {
            "find_official_annual_report": ("年报", "巨潮"),
            "search_company_filings": ("年报", "公告", "财报原文"),
            "get_fuyao_cash_flow": ("现金流",),
            "get_cash_flow": ("现金流",),
            "get_fuyao_balance_sheet": ("资产负债",),
            "get_balance_sheet": ("资产负债",),
            "get_financial_summary": ("利润表",),
            "get_market_snapshot": ("行情", "股价", "价格走势"),
            "get_valuation_snapshot": ("估值", "市盈率", "市净率"),
        }
        for instruction in re.split(r"[，,。；;\n]+", feedback):
            instruction = instruction.strip()
            if not instruction:
                continue
            if match := re.fullmatch(r"(?:不要|不需要|不用|不查|跳过|取消|去掉|移除)[查找看取数询]*\s*(.+)", instruction):
                target = match[1]
                matches = {task["tool_name"] for task in tasks if target in task["title"]
                           or any(alias in target for alias in aliases.get(task["tool_name"], ()))}
                if matches:
                    removed.update(matches)
                    continue
            if match := re.fullmatch(r"(?:改为|改成|改做|换成)[：:\s]*(.+)", instruction):
                updated = match[1]
                if updated in {"估值", "盈利能力", "风险", "综合研究"}:
                    updated = f"分析{resolve_symbol(goal)}的{updated}"
                goal = updated
                continue
            if match := re.fullmatch(r"(?:只看|只分析|重点看|重点分析)(盈利能力|盈利|估值|风险)", instruction):
                goal = f"分析{resolve_symbol(goal)}的{match[1]}"
                continue
            raise AppError(status_code=422, code="unsupported_plan_feedback",
                           message="暂未识别这条修改意见。可以输入「取消官方年报」或「改为估值」，也可以展开下方选项直接改写研究要求。")
        return goal, removed

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
        from app.services.jobs import enqueue
        with self.store.connection() as con:
            changed = con.execute("UPDATE runs SET status='APPROVED',approval_json=?,updated_at=? WHERE id=? AND status='PENDING_APPROVAL' AND plan_version=?", (json.dumps(approval_data), now_iso(), run_id, approval.plan_version))
            if changed.rowcount != 1:
                raise AppError(status_code=409, code='approval_state_changed', message='研究已被其他请求更新。')
            enqueue(con, run_id)
        self._event(run_id, "plan.approved", approval_data)
        return await self._dispatch(run_id)

    def reject(self, run_id: str, rejection: RejectRequest) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] != "PENDING_APPROVAL" or rejection.plan_version != run["plan_version"]:
            raise AppError(status_code=409, code="rejection_not_allowed", message="Run or plan version cannot be rejected.")
        timestamp = now_iso()
        with self.store.connection() as con:
            changed = con.execute(
                """UPDATE runs SET status='REJECTED',error=?,updated_at=?,completed_at=?
                   WHERE id=? AND status='PENDING_APPROVAL' AND plan_version=?""",
                (rejection.reason, timestamp, timestamp, run_id, rejection.plan_version),
            )
            if changed.rowcount != 1:
                raise AppError(status_code=409, code="rejection_not_allowed", message="Run or plan version cannot be rejected.")
        self._event(run_id, "plan.rejected", {"plan_version": rejection.plan_version, "reason": rejection.reason})
        self._save_checkpoint(run_id, "REJECTED")
        return self.get_run(run_id)

    async def execute(self, run_id: str, retry_task_ids: set[str] | None = None, lease_token: str | None = None) -> dict[str, Any]:
        if lease_token is None:
            raise AppError(status_code=409, code="worker_lease_required", message="Execution must be claimed by a worker.")
        from app.services.executor import execute
        return await execute(self, run_id, retry_task_ids, lease_token)

    async def _dispatch(self, run_id: str) -> dict[str, Any]:
        if self.settings.execution_mode == 'inline':
            from app.services.jobs import process_one
            await process_one(self, run_id)
        return self.get_run(run_id)

    def finish_report(self, run_id, status, stop_reason):
        from app.services.research_review import review_research
        from app.services.report_validation import attach_validation
        run = self.get_run(run_id)
        evidence = self.get_evidence(run_id)
        report = self._build_report(run_id, status, stop_reason)
        report['research_review'] = review_research(run['goal'], run['tasks'], evidence, self.registry,
            self.settings.research_data_dir, run['supplement_rounds'], self.settings.max_supplement_rounds,
            annual_year=run['tasks'][0]['arguments']['fiscal_year'] if run['planner_mode'] == 'annual_update' else None)
        report['coverage_status'] = report['research_review']['coverage_status']
        if run['planner_mode'] == 'annual_update':
            from app.services.annual_evidence import annual_answers
            report['annual_answers'] = annual_answers(evidence, run['tasks'][0]['arguments']['fiscal_year'])
        elif report['research_review']['research_type'] == 'profitability':
            from app.services.annual_evidence import annual_answers
            income = next((item for item in evidence if item['tool_name'] == 'get_financial_summary'
                           and not item['is_demo'] and item['data'].get('quality', {}).get('usable', True)), None)
            if income and income['data'].get('fiscal_year'):
                report['annual_answers'] = annual_answers(evidence, income['data']['fiscal_year'])[2:]
        supplemental = {e['tool_name'] for e in evidence if e['data'].get('dataset') and e['data'].get('quality', {}).get('usable', True)}
        if supplemental:
            labels = sorted({e['data'].get('data_label', 'DEMO DATA' if e['is_demo'] else 'UNSPECIFIED SOURCE') for e in evidence})
            report['data_notice'] = ' · '.join(labels) + '；各条证据来源与时点独立；演示样本不得用作真实判断。'
            report['missing_information'] = [message for message in report['missing_information']
                if not any(text in message for text in ('缺少历史估值区间、同业比较及完整财务报表', 'PB 为 MRQ 口径；本接口不提供', '利润表不提供 ROE；未取得资产负债表与现金流量表'))]
            if any(e['data'].get('data_label') == 'IMPORTED PUBLIC SOURCES' for e in evidence):
                report['missing_information'].append('导入资料仅覆盖提供的样本；仍需核验可比性、新鲜度和覆盖完整性。')
            if {'get_valuation_history','get_peer_valuations'} <= supplemental:
                for finding in report['findings']:
                    finding['statement'] = finding['statement'].replace('缺少同业和历史区间，不能单凭倍数认定低估或高估。', '另有导入历史与同业样本；样本完整性及可比性尚未独立核验，不能单凭倍数认定低估或高估。')
        if run['planner_mode'] == 'annual_update' and 'search_company_filings' in report['research_review']['unanswered_questions']:
            report['findings'].append({
                'task': '管理层解释', 'statement': '尚无匹配报告期的可用原文，无法核对管理层对盈利变化的解释。',
                'evidence_ids': [],
            })
        report['missing_information'].extend(report['research_review']['missing_evidence'])
        return attach_validation(report, evidence)

    def propose_supplement(self, run_id, expected_updated_at, plan_version, *, uploaded_task=None):
        run = self.get_run(run_id)
        if run['status'] not in {'COMPLETE', 'PARTIAL'} or run['updated_at'] != expected_updated_at or run['plan_version'] != plan_version:
            raise AppError(status_code=409, code='supplement_state_changed', message='研究状态已变化，请刷新后重试。')
        if len(self.get_tool_calls(run_id)) >= self.settings.max_tool_calls or run['execution_seconds'] >= self.settings.run_timeout_seconds:
            return run
        from app.services.research_review import review_research
        review = review_research(run['goal'], run['tasks'], self.get_evidence(run_id), self.registry,
            self.settings.research_data_dir, run['supplement_rounds'], self.settings.max_supplement_rounds,
            annual_year=run['tasks'][0]['arguments']['fiscal_year'] if run['planner_mode'] == 'annual_update' else None)
        proposed = [uploaded_task] if uploaded_task else review['proposed_tasks']
        if uploaded_task and (run['planner_mode'] != 'annual_update'
                or run['supplement_rounds'] >= self.settings.max_supplement_rounds
                or len(run['tasks']) >= 8):
            raise AppError(status_code=409, code='upload_supplement_unavailable', message='本次研究无法继续补查。')
        if not proposed:
            return run
        data = dict(run['plan'])
        data['tasks'] = [*data['tasks'], *proposed]
        data['scope'] = [*data.get('scope', []), *(t['title'] for t in proposed)]
        plan = ResearchPlan.model_validate(data)
        for task in plan.tasks:
            self.registry.validate(task.tool_name, task.arguments)
        timestamp, version = now_iso(), plan_version + 1
        with self.store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            changed = con.execute("UPDATE runs SET status='PENDING_APPROVAL',plan_version=?,plan_json=?,approval_json=NULL,supplement_rounds=supplement_rounds+1,updated_at=?,completed_at=NULL WHERE id=? AND updated_at=? AND plan_version=? AND status IN ('COMPLETE','PARTIAL')",
                (version, json.dumps(plan.model_dump(), ensure_ascii=False), timestamp, run_id, expected_updated_at, plan_version))
            if changed.rowcount != 1:
                raise AppError(status_code=409, code='supplement_state_changed', message='研究已被其他请求更新。')
            con.execute('UPDATE tasks SET plan_version=? WHERE run_id=?', (version, run_id))
            for position, task in enumerate(plan.tasks[len(run['tasks']):], len(run['tasks']) + 1):
                con.execute("INSERT INTO tasks(id,run_id,plan_version,position,title,tool_name,arguments_json,rationale,status,created_at,updated_at,task_key,depends_on_json) VALUES(?,?,?,?,?,?,?,?,'PENDING',?,?,?,?)",
                    (str(uuid4()), run_id, version, position, task.title, task.tool_name, json.dumps(task.arguments, ensure_ascii=False), task.rationale, timestamp, timestamp, task.task_key, json.dumps(task.depends_on)))
        self._event(run_id, 'plan.supplement_proposed', {'plan_version': version, 'new_tasks': proposed, 'approval_required': True})
        return self.get_run(run_id)

    def _record_tool_call(self, run_id: str, task: dict[str, Any], attempt: int, status: str, duration: float, result: dict[str, Any] | None, error: str | None) -> None:
        self.store.execute("INSERT INTO tool_calls(id,run_id,task_id,tool_name,attempt,status,duration_ms,result_json,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(uuid4()), run_id, task["id"], task["tool_name"], attempt, status, duration, json.dumps(result, ensure_ascii=False) if result else None, error, now_iso()))

    def _fail_task(self, task: dict[str, Any], error: str) -> None:
        self.store.execute("UPDATE tasks SET status='FAILED',error=?,updated_at=? WHERE id=?", (error, now_iso(), task["id"]))

    def _build_report(self, run_id: str, status: str, stop_reason: str | None) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        tasks = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))
        evidence = self.store.fetch_all("SELECT * FROM evidence WHERE run_id=? ORDER BY created_at", (run_id,))
        annual_update = run['planner_mode'] == 'annual_update'
        if annual_update or any(not item["is_demo"] for item in evidence) or any(tool["data_source"] == "FUYAO / MARKET DATA" for tool in self.registry.schemas()):
            focus = (run.get("plan") or {}).get("research_type", "comprehensive")
            scope = (run.get("plan") or {}).get("scope") or [task["title"] for task in tasks]
            focus_title = {"profitability": "盈利能力初步研究", "valuation": "估值初步研究", "risk": "风险线索初步研究", "comprehensive": "综合研究摘要"}[focus]
            symbols = {task["arguments"].get("symbol") for task in tasks}
            is_bank = bool(symbols & {"600036.SH", "000001.SZ"})
            bank_risk = is_bank and ("风险" in run["goal"] or "risk" in run["goal"].lower())
            findings = []
            missing = [task["title"] + ": " + str(task.get("error") or "未完成") for task in tasks if task["status"] != "COMPLETED"]
            if annual_update:
                missing.extend((run.get("plan") or {}).get("limitations", [])[:1])
            def number(value):
                return "未提供" if value is None else f"{value:,.2f}"
            for item in evidence:
                data = item["data"]
                quality = data.get("quality") or {}
                for issue in quality.get("issues", []):
                    missing.append(f"[{item['id']}] {issue['message']}")
                if quality.get("usable") is False:
                    findings.append({"task": item["title"], "statement": "此证据未通过质量检查，已排除出指标、图表及正常研究结论。原始响应保留供复核；请核验数据后新建研究。", "evidence_ids": [item["id"]]})
                    continue
                if item["is_demo"]:
                    statement = "DEMO DATA：此条为演示证据，不可用于真实结论。"
                elif data.get('dataset'):
                    count = len(data.get('records', []))
                    statement = f"{data.get('data_label', '导入公开资料')}：{item['title']}，取得 {count} 条带来源与口径的记录。尚未独立交叉核验。"
                    if data.get('dataset') == 'filings':
                        statement = '找到相关年报原文。请核对下方摘录及其上下文，判断是否解释了具体的盈利变化。'
                    if data.get('statistics'):
                        stats = data['statistics']
                        statement += f"样本 PE(TTM) 区间 {stats['min_pe_ttm']:.2f}–{stats['max_pe_ttm']:.2f} 倍；不代表全历史区间。"
                    if data.get("data_label") == "FUYAO / MARKET DATA" and data["records"]:
                        latest = data["records"][-1]
                        if data["dataset"] == "cash_flows":
                            statement += f" {latest['period']} 年度经营活动现金流量净额 {number(latest['operating_cash_flow'] / 1e8)} 亿元。"
                        elif data["dataset"] == "balance_sheets":
                            statement += f" {latest['period']} 总资产 {number(latest['total_assets'] / 1e8)} 亿元，总负债 {number(latest['total_liabilities'] / 1e8)} 亿元。"
                elif "snapshot" in data:
                    row = data["snapshot"]
                    statement = f"扶摇行情快照：价格 {number(row.get('price_cny'))} 元，涨跌幅 {number(row.get('change_percent'))}%。取得 {len(data.get('prices', []))} 条前复权日线。接口时间（北京时间）{datetime.fromtimestamp(data['timestamp_ms']/1000, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S') if isinstance(data.get('timestamp_ms'), (int, float)) else '未提供'}；接口时间不保证等于最新成交时间。"
                elif "valuation" in data:
                    row = data["valuation"]
                    statement = f"估值：PE(TTM) {number(row.get('pe_ttm'))} 倍，PB(MRQ) {number(row.get('pb'))} 倍。倍数反映市场定价，缺少同业和历史区间，不能单凭倍数认定低估或高估。"
                else:
                    rows = data.get("financial_history", [])
                    latest = rows[-1] if rows else {}
                    statement = f"盈利：{latest.get('year', '最近年度')} 年营业收入 {number(latest.get('revenue'))} 亿元，归母净利润 {number(latest.get('profit'))} 亿元。"
                    if annual_update and len(rows) < 2:
                        statement += ' 未取得可比较的上年完整数据，无法判断年度变化。'
                    if annual_update and len(rows) > 1:
                        previous = rows[-2]
                        statement += f" 上年营业收入 {number(previous.get('revenue'))} 亿元，归母净利润 {number(previous.get('profit'))} 亿元。"
                    if len(rows) > 1 and rows[-2].get('revenue') and latest.get('revenue') is not None:
                        growth = (latest['revenue'] / rows[-2]['revenue'] - 1) * 100
                        statement += f"营业收入较上一可用年度变化 {growth:.2f}%；"
                        statement += "银行盈利需结合净息差、信用减值与非息收入验证，利润表总额不足以判断资产质量。" if is_bank else "需结合现金回款验证盈利质量。"
                notices = [issue["message"] for issue in quality.get("issues", []) if issue["code"] in {"TIME_STALE", "HISTORY_STALE", "TIME_MISSING", "FINANCIAL_STALE", "PERIOD_GAP", "VALUATION_NONPOSITIVE"}]
                if notices:
                    statement += " 质量提示：" + "；".join(notices)
                findings.append({"task": item["title"], "statement": statement, "evidence_ids": [item["id"]]})
                if data.get("missing_information") and not (focus == "profitability" and item["tool_name"] == "get_financial_summary"):
                    missing.append(data["missing_information"])
            if focus == "profitability" and not annual_update:
                usable = {item["tool_name"]: item for item in evidence
                          if not item["is_demo"] and item["data"].get("available", True)
                          and item["data"].get("quality", {}).get("usable", True)}
                income = usable.get("get_financial_summary")
                if income and (rows := income["data"].get("financial_history")):
                    latest = rows[-1]
                    profit = latest.get("profit")
                    revenue = latest.get("revenue")
                    if profit is not None and revenue and revenue > 0:
                        findings.append({"task": "归母净利润占营收比例",
                                         "statement": f"{latest['year']} 年为 {profit / revenue:.2%}。",
                                         "evidence_ids": [income["id"]]})
                    cash = usable.get("get_fuyao_cash_flow")
                    if cash and profit and profit > 0:
                        matching = next((row for row in cash["data"]["records"]
                                         if row["period"] == f"{latest['year']}-12-31"), None)
                        if matching:
                            ratio = matching["operating_cash_flow"] / (profit * 1e8)
                            findings.append({"task": "经营现金流与归母净利润对照",
                                             "statement": f"{latest['year']} 年经营活动现金流量净额相当于归母净利润的 {ratio:.2%}。两项口径不同，比例用于观察现金流与利润的关系。",
                                             "evidence_ids": [cash["id"], income["id"]]})
            if bank_risk:
                findings.append({"task": "银行风险研究覆盖", "statement": "现有证据仅覆盖价格、年度营收与利润、估值倍数。尚未取得不良贷款率、关注及逾期贷款、拨备覆盖率、净息差、核心一级资本充足率和重点行业贷款敞口，无法判断资产质量、资本缓冲或流动性风险。以下为待核验方向，不代表这些风险已发生。", "evidence_ids": []})
            if is_bank:
                missing.extend(["银行专属数据缺失：不良贷款率、关注及逾期贷款、拨备覆盖率、净息差、核心一级资本充足率、流动性指标与房地产等重点行业贷款敞口。", "待核验风险：资产质量变化、信用减值压力、净息差变化及资本与流动性缓冲；不能从现有利润表推断风险已发生。", "PB 低于 1 不自动代表低估，需结合 ROE、资产质量、资本要求与历史同业比较。"])
            elif not annual_update and focus != "profitability":
                missing.append("风险待验证：需求与渠道回款走弱可能影响利润；利率或风险偏好变化可能压缩估值。")
            missing.extend(["扶摇接口数据尚未与交易所原始公告交叉核验。", "年度比较仍需核对报表口径、会计调整及可比性；变化原因需看年报原文。"])
            if focus != "profitability":
                missing.append("估值须结合历史区间、同业及财务口径核对。")
            if stop_reason:
                missing.append(stop_reason)
            quality_rows = [{"evidence_id": item["id"], **item["data"]["quality"]} for item in evidence if item["data"].get("quality")]
            quality_status = "FAIL" if any(row["status"] == "FAIL" for row in quality_rows) else "WARN" if any(row["status"] == "WARN" for row in quality_rows) else "PASS" if quality_rows else "NOT_CHECKED"
            return {"title": f"{'银行风险初步研究' if bank_risk else focus_title}：{run['goal']}", "status": status, "data_notice": "DEMO DATA · 演示证据不可用于真实判断。" if evidence and all(item["is_demo"] for item in evidence) else "各条证据的来源、报告期和质量以引用为准。", "coverage_status": "LIMITED", "quality_status": quality_status, "quality_checks": quality_rows, "executive_summary": f"取得 {len(evidence)}/{len(tasks)} 项证据，其中 {sum(item['data'].get('quality', {}).get('usable', True) for item in evidence)} 项未被质量检查阻断。本次范围：{'；'.join(scope)}。报告仅依据取得的证据整理；关键发现需结合来源核对。", "findings": findings, "missing_information": list(dict.fromkeys(missing)), "evidence_ids": [item["id"] for item in evidence]}
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

    async def retry_failed(self, run_id: str, request: RetryFailedRequest) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] not in {"PARTIAL", "FAILED"}:
            raise AppError(status_code=409, code="retry_not_allowed", message="仅部分完成或执行失败的研究可重试失败任务。")
        if run["updated_at"] != request.expected_updated_at or run["plan_version"] != request.plan_version:
            raise AppError(status_code=409, code="retry_state_changed", message="研究状态或计划已更新，请刷新后再操作。")
        approval = run.get("approval")
        if not approval or approval.get("plan_version") != run["plan_version"]:
            raise AppError(status_code=409, code="approval_required", message="缺少有效原审批；规划失败请新建研究，不能直接执行工具。")
        failed = self.store.fetch_all("SELECT * FROM tasks WHERE run_id=? AND status='FAILED' ORDER BY position", (run_id,))
        if not failed:
            raise AppError(status_code=409, code="no_failed_tasks", message="没有可重试的失败任务；未完成步骤请使用恢复。")
        if len(self.get_tool_calls(run_id)) >= self.settings.max_tool_calls:
            raise AppError(status_code=409, code="retry_budget_exhausted", message="本次研究的工具调用预算已耗尽；不会重置预算或重复查询。")
        original_tasks = (run.get("plan") or {}).get("tasks", [])
        for task in failed:
            position = task["position"] - 1
            original = original_tasks[position] if 0 <= position < len(original_tasks) else {}
            if (task["plan_version"] != run["plan_version"] or task["tool_name"] not in approval["allowed_tools"]
                    or original.get("tool_name") != task["tool_name"] or original.get("arguments") != task["arguments"]):
                raise AppError(status_code=409, code="retry_scope_changed", message="任务已超出原计划或审批范围，禁止重试。")
            try:
                self.registry.validate(task["tool_name"], task["arguments"])
            except ValueError:
                raise AppError(status_code=409, code="retry_invalid_task", message="失败任务工具或参数无效，禁止重试。") from None
        timestamp = now_iso()
        with self.store.connection() as connection:
            claimed = connection.execute("UPDATE runs SET status='APPROVED',error=NULL,completed_at=NULL,updated_at=? WHERE id=? AND status=? AND updated_at=?", (timestamp, run_id, run["status"], request.expected_updated_at))
            if claimed.rowcount != 1:
                raise AppError(status_code=409, code="retry_state_changed", message="研究正在被其他请求更新，请刷新后再操作。")
            connection.execute("INSERT INTO events(run_id,event_type,data_json,created_at) VALUES(?,?,?,?)", (run_id, "run.retry_requested", json.dumps({"task_ids": [task["id"] for task in failed], "plan_version": run["plan_version"], "attempts_per_task": 1}, ensure_ascii=False), timestamp))
            if run.get("report"):
                connection.execute("INSERT INTO events(run_id,event_type,data_json,created_at) VALUES(?,?,?,?)", (run_id, "report.archived", json.dumps({"reason": "retry_failed", "report": run["report"]}, ensure_ascii=False), timestamp))
            from app.services.jobs import enqueue
            enqueue(connection, run_id, {task['id'] for task in failed})
        self._save_checkpoint(run_id, "APPROVED")
        result = await self._dispatch(run_id)
        return result

    async def resume(self, run_id: str) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] == "COMPLETE":
            return self.get_run(run_id)
        if run["status"] not in {"APPROVED", "RUNNING", "PARTIAL", "FAILED"}:
            raise AppError(status_code=409, code="resume_not_allowed", message="Run cannot be resumed in its current state.")
        from app.services.jobs import enqueue
        with self.store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            active = con.execute("SELECT state,lease_until FROM run_jobs WHERE run_id=?", (run_id,)).fetchone()
            if active and active['state'] in {'QUEUED','RUNNING'}:
                return self.get_run(run_id)
            if not run.get('approval') or run['approval']['plan_version'] != run['plan_version']:
                raise AppError(status_code=409, code='approval_required', message='A matching approval is required.')
            con.execute("UPDATE tasks SET status='PENDING' WHERE run_id=? AND status IN ('RUNNING','BLOCKED')", (run_id,))
            con.execute("UPDATE runs SET status='APPROVED',updated_at=? WHERE id=?", (now_iso(), run_id))
            enqueue(con, run_id)
        self._event(run_id, "run.resumed", {"checkpoint_loaded": bool(self.get_checkpoints(run_id))})
        return await self._dispatch(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        run = self._run_or_404(run_id)
        if run["status"] in {"COMPLETE", "REJECTED", "CANCELLED"}:
            raise AppError(status_code=409, code="cancel_not_allowed", message="Run is already terminal.")
        with self.store.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            changed = con.execute("UPDATE runs SET status='CANCELLED',updated_at=?,completed_at=? WHERE id=? AND status NOT IN ('COMPLETE','REJECTED','CANCELLED')", (now_iso(), now_iso(), run_id))
            if changed.rowcount != 1:
                raise AppError(status_code=409, code='cancel_not_allowed', message='Run is already terminal.')
            con.execute("UPDATE run_jobs SET state='CANCELLED',lease_until=NULL WHERE run_id=?", (run_id,))
            con.execute("UPDATE tasks SET status='CANCELLED',error='Cancelled by user',updated_at=? WHERE run_id=? AND status IN ('PENDING','RUNNING','BLOCKED')", (now_iso(), run_id))
            con.execute("UPDATE tool_calls SET status='CANCELLED',error='Cancelled; late read-only response will not be committed' WHERE run_id=? AND status='STARTED'", (run_id,))
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

    def list_threads(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        threads = self.store.fetch_all("SELECT * FROM threads WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,))
        for thread in threads:
            thread["memory"] = self.get_memory(thread["id"])
            thread["runs"] = self.store.fetch_all("SELECT id,goal,status,planner_mode,created_at,updated_at FROM runs WHERE thread_id=? ORDER BY created_at DESC", (thread["id"],))
        return threads

    def list_tools(self) -> list[dict[str, Any]]:
        return self.registry.schemas()


def build_run_service(settings: Settings) -> RunService:
    from app.services.fuyao import build_fuyao_registry
    registry = build_fuyao_registry(settings.fuyao_api_key) if settings.finance_provider_configured else build_tool_registry()
    from app.services.research_sources import register_source_tools
    register_source_tools(registry, settings.research_data_dir)
    from app.services.official_filings import register_official_filings
    if settings.finance_provider_configured:
        register_official_filings(registry)
    planner: Planner = FixturePlanner() if settings.planner_mode == "fixture" else DeepSeekPlanner(settings, registry)
    return RunService(settings, SQLiteStore(settings.sqlite_path), registry, planner)


@lru_cache
def get_run_service() -> RunService:
    return build_run_service(get_settings())

