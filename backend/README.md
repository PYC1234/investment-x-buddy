# Investment X Buddy Backend

Runnable FastAPI research-agent backend. The planner uses DeepSeek by default;
tests inject a fixture planner and never make paid requests. All bundled finance
tools return clearly marked **FIXTURE / DEMO DATA**.

## Start locally

From the repository root in PowerShell:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for OpenAPI. SQLite defaults to
`backend/data/investment_x_buddy.db`.

## Environment variables

The application reads the repository-root `.env`. Secrets are never returned.

| Variable | Required | Default / purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` | For real planner | DeepSeek credential |
| `DEEPSEEK_BASE_URL` | For real planner | Existing root configuration |
| `DEEPSEEK_MODEL` | For real planner | Existing root configuration (`deepseek-flash`) |
| `PLANNER_MODE` | No | `deepseek`; set exactly `fixture` for explicit demo fallback |
| `SQLITE_PATH` | No | `backend/data/investment_x_buddy.db` |
| `CORS_ORIGINS` | No | JSON array such as `["http://localhost:3000","https://app.example.com"]` |
| `MAX_TOOL_CALLS` | No | `8` |
| `MAX_EXECUTION_ROUNDS` | No | `8` |
| `RUN_TIMEOUT_SECONDS` | No | `30` |
| `MAX_TOOL_RETRIES` | No | `1` |
| `DEEPSEEK_INPUT_COST_PER_1M` | No | Optional cost-estimation price |
| `DEEPSEEK_OUTPUT_COST_PER_1M` | No | Optional cost-estimation price |

Absent prices produce `cost_status=NOT_CONFIGURED`; the API does not guess
provider pricing. CORS never enables a wildcard origin.

## Main workflow

1. `POST /api/v1/runs` invokes the configured planner and persists a
   `PENDING_APPROVAL` run.
2. The UI displays `plan`, `tasks`, `plan_version`, and `planner_mode`.
3. Approval repeats the current plan version and supplies a tool allowlist that
   covers every planned task.
4. `POST /api/v1/runs/{id}/approve` executes synchronously and returns
   `COMPLETE` or `PARTIAL`.
5. The UI reads evidence, report, events, tasks, checkpoints, and memory.

No tool executes before approval. Resume reads persisted state and skips completed
tasks.

## API contract

### Create a run

`POST /api/v1/runs`

```json
{
  "goal": "Analyze Kweichow Moutai profitability and valuation",
  "thread_id": null,
  "thread_title": "Moutai research",
  "preferences": {"risk_style": "conservative"}
}
```

Response `201` is a Run object:

```json
{
  "id": "uuid",
  "thread_id": "uuid",
  "goal": "...",
  "status": "PENDING_APPROVAL",
  "plan_version": 1,
  "planner_mode": "deepseek",
  "plan": {
    "research_goal": "...",
    "tasks": [
      {
        "title": "...",
        "tool_name": "get_market_snapshot",
        "arguments": {"symbol": "600519.SH"},
        "rationale": "..."
      }
    ]
  },
  "approval": null,
  "report": null,
  "tasks": [],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "estimated_cost_usd": null,
    "cost_status": "NOT_CONFIGURED"
  }
}
```

Statuses: `PLANNING`, `PENDING_APPROVAL`, `APPROVED`, `RUNNING`,
`COMPLETE`, `PARTIAL`, `FAILED`, `REJECTED`, `CANCELLED`.

### Read and control a run

| Method | Path | Body / result |
|---|---|---|
| `GET` | `/api/v1/runs/{id}` | Full Run object with tasks |
| `POST` | `/api/v1/runs/{id}/approve` | Approval body below; executes plan |
| `POST` | `/api/v1/runs/{id}/reject` | `{"plan_version":1,"reason":"..."}` |
| `POST` | `/api/v1/runs/{id}/resume` | No body; skips completed tasks |
| `POST` | `/api/v1/runs/{id}/cancel` | No body |

```json
{
  "plan_version": 1,
  "allowed_tools": [
    "get_market_snapshot",
    "get_financial_summary",
    "get_valuation_snapshot"
  ]
}
```

Approval returns `409` for a stale version and `400` for an unregistered or
incomplete scope.

### Run artifacts and discovery

| Method | Path | Result |
|---|---|---|
| `GET` | `/api/v1/runs/{id}/events` | Ordered JSON event array |
| `GET` | `/api/v1/runs/{id}/report` | Evidence-linked report; `409` before ready |
| `GET` | `/api/v1/runs/{id}/evidence` | Evidence items with `id`, `data`, `is_demo` |
| `GET` | `/api/v1/runs/{id}/tasks` | Task state, attempts, error, evidence ID |
| `GET` | `/api/v1/runs/{id}/checkpoints` | State and compression size records |
| `GET` | `/api/v1/runs/{id}/tool-calls` | Every attempt with status, duration, result/error |
| `GET` | `/api/v1/runs/{id}/memory` | Thread research preferences |
| `GET` | `/api/v1/threads` | Threads, runs, and persisted memory |
| `GET` | `/api/v1/tools` | Registered JSON schemas and DEMO DATA label |
| `GET` | `/api/v1/health` | Service status/version/timestamp |
| `GET` | `/api/v1/config/capabilities` | Non-sensitive configuration flags |
| `GET` | `/api/v1/events/demo` | Finite SSE demonstration stream |

Persisted run events are JSON for replay. The separate demo endpoint uses
`text/event-stream`.

### Error envelope

```json
{
  "error": {
    "code": "approval_required",
    "message": "A matching plan approval is required before execution.",
    "request_id": "uuid"
  }
}
```

Validation details include locations and types but omit submitted values.

## Fixture tools

- `get_market_snapshot(symbol, simulate_failure=false)`
- `get_financial_summary(symbol, fiscal_year, simulate_failure=false)`
- `get_valuation_snapshot(symbol, simulate_failure=false)`

Symbols must match `NNNNNN.SH` or `NNNNNN.SZ`. Unknown fixtures return
`available=false` and `missing_information`. The explicit
`simulate_failure=true` path demonstrates retry and `PARTIAL`.

## Tests

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q
```

Tests use temporary SQLite databases and a Mock/Fixture Planner. They cover the
full create-plan-approve-execute-evidence-report path, restart persistence,
resume without duplicate work, approval enforcement, argument validation,
retry/PARTIAL behavior, budget stopping, compression, memory, CORS, SSE, and
secret-safe errors.

## Deployment

Set the Render or Railway service root directory to `backend`. The included
`Procfile` starts Uvicorn using the platform `PORT`. Configure
`CORS_ORIGINS` with the deployed frontend and store DeepSeek values as secrets.

SQLite persists across restarts only when `SQLITE_PATH` points to a mounted
persistent disk. Ephemeral cloud filesystems can discard it during restart or
redeploy. Use one Uvicorn worker for this SQLite demo. Production multi-worker
execution needs a managed database and job queue.

## Implemented

- Real DeepSeek JSON planner and explicit fixture planner mode
- Version-bound, tool-scoped approval and rejection
- Registered-tool allowlist and Pydantic parameter validation
- Three executable fixture finance tools
- Evidence-linked deterministic report with missing-data disclosure
- Per-attempt latency/error logs, tokens, configurable cost estimate
- Tool-call, round, retry, and wall-time stop rules
- SQLite runs, tasks, events, evidence, tool calls, checkpoints, and memory
- Restart read/resume without repeating completed tasks
- Context-compression records with before/after sizes
- Simulated provider failure and PARTIAL result

## Not implemented

- Additional financial providers beyond the implemented Fuyao tools
- Authentication, tenant isolation, or user accounts
- Distributed worker queue and cross-process cancellation guarantees
- Live SSE streaming for persisted run events
- Automatic cloud disk provisioning or PostgreSQL migration
- LLM-written report prose; reports are deterministic and evidence-safe



## 扶摇真实数据模式
Render Environment 配置 `FUYAO_API_KEY`，部署本版本并重启后，工具自动使用扶摇真实只读接口。`PLANNER_MODE=fixture` 可继续保留：仅计划使用目标分类规则，金融证据使用真实接口，不调用收费 DeepSeek。
三个工具分别读取行情快照（附一年日线）、最近五个年度利润表和估值快照。每次完整审批执行通常产生四个 HTTP 请求；失败不切回演示数据。可设置 `MAX_TOOL_RETRIES=0` 禁止失败后重复工具请求。
前端 `NEXT_PUBLIC_API_BASE_URL=https://investment-x-buddy.onrender.com`，修改后重新构建。旧 Run 的证据不会被替换，请创建并审批新研究。图表来自日线和年度利润表；ROE 未提供时显示空值。非交易时段显示最近可用行情，不能保证逐笔实时。
报告使用可追溯证据生成规则分析，不调用报告 LLM；SQLite 云端持久化仍需持久磁盘。


## 单只 A 股标的识别
固定计划不再默认查询茅台。在 `goal` 中填写六位沪深 A 股代码（如 `300750.SZ`、`600036.SH` 或 `600900`），全部任务使用同一代码。小型名称表支持贵州茅台/茅台、宁德时代、平安银行、五粮液、招商银行/招行、中国平安及 Moutai/CATL；不是全市场模糊搜索。
一次只支持一只股票。未识别、多个标的、名称与代码冲突或交易所后缀不符，返回 422 `invalid_symbol`，不会默认查询茅台。不支持港股和北交所；代码格式通过不代表证券一定存在或供应商有数据，无记录会明确失败。没有扶摇 Key 的 Fixture 数据仍只覆盖原有演示标的。


## 报告研究覆盖
真实数据报告返回 `coverage_status=LIMITED`；COMPLETE 只表示任务执行完成。招商银行与平安银行的风险研究会列出银行指标缺失和待核验方向，不把缺少的数据写成已发生风险。历史报告保持原样，新报告在新 Run 执行后生成。
前端映射回归测试：在 frontend 目录执行 `node --import tsx --test tests/research-gateway.test.ts`。


## 按目标规划与确认范围
FixturePlanner 使用确定性关键词规则：单一盈利目标只查询利润表；单一估值目标查询估值和利润表；风险目标或多个目标查询行情、利润表、估值。无明确分类时为综合研究；不新增付费模型调用。
Plan 新增兼容字段 `research_type`（profitability/valuation/risk/comprehensive）、`scope`、`limitations`，前端 Plan 页在审批前显示研究确认卡。未支持的风险数据明确列为缺口，不创建假工具任务。报告摘要列出本次实际计划范围。
固定验收集见 `tests/test_research_scope.py`、`tests/test_symbols.py`、`tests/test_bank_report.py` 及前端 `tests/research-gateway.test.ts`。此分类器不等同于自由语义规划；名称主数据覆盖及银行专属指标仍有限。


## 失败任务一键重试
`POST /api/v1/runs/{id}/retry-failed`，请求体：
```json
{"plan_version":1,"expected_updated_at":"GET Run 返回的完整 updated_at 字符串"}
```
仅对 PARTIAL/FAILED Run 内 FAILED 任务执行；必须有匹配原审批，任务工具、参数和版本须与原计划完全一致。不允许传入新参数。每次手动重试每个失败项最多一次，跳过成功和其他未完成任务；累计 attempts 和工具调用预算不重置。部分预算不足时，未尝试的失败项仍保留失败原因。
成功返回 200 和更新后的完整 Run/报告；再次失败保持 PARTIAL。409 错误包括 retry_not_allowed、retry_state_changed、approval_required、no_failed_tasks、retry_budget_exhausted、retry_scope_changed、retry_invalid_task。旧状态请求和重复点击不能重复执行同一状态的重试。
旧报告保存在 `report.archived` 事件中，重试记录为 `run.retry_requested` / `run.retry_completed`，每次工具尝试有独立耗时、错误、结果；检查点继续持久化。工具次数为整个 Run 的累计限制，轮数和执行超时仍按每次执行批次生效；并非硬实时截止。
前端 Plan 页列出失败任务与错误，并提供“重试失败任务”。纯规划失败没有工具审批时不可用，应新建研究；中断但未失败的任务继续使用 resume。尚无分布式任务锁或后台队列。
验收：`.venv/Scripts/python.exe -m pytest tests/test_retry_failed.py -q`，测试注入首次失败后成功、持续失败、预算耗尽、重复请求、参数变更和同库重启恢复，不调用收费模型或真实金融服务。

## 证据质量检查（2026-10-12）
新 Run 的真实 Evidence 在执行后保存 `data.quality`：
```json
{"version":1,"checked_at":"ISO 8601","status":"WARN","usable":true,"issues":[{"code":"TIME_STALE","field":"timestamp_ms","severity":"WARN","message":"来源超过提醒阈值"}],"policy":"接口级规则检查"}
```
检查证券一致性、已提供的供应商证券/币种、来源时间、关键指标、历史序列、年度连续性以及字段单位/口径契约。行情/估值超过 7 个自然日仅提示陈旧，不假设节假日或停牌规则；年度数据超过两年提醒陈旧。超过当前时间 5 分钟、币种冲突、非法数值、全量关键数据缺失、未来财务期间等严重问题标为 FAIL/usable=false。
FAIL 不触发自动重查，原始数据保留供复核；成功取数的 Task 仍是 COMPLETED，但 Run 为 PARTIAL，异常证据不进入正常报告结论及前端指标/图表。修正问题后新建研究，不用失败任务重试绕过质量规则。
报告新增兼容字段 `quality_status` 与 `quality_checks`，限制区展示带 Evidence ID 的问题；事件 `evidence.quality_checked` 记录结果。前端旧报告显示未检查，不伪造历史验收。
扶摇 Evidence 保存 `field_provenance`（raw_field/unit/basis）、原始快照与日线。字段映射来自适配契约，不能代替供应商内容真实性、交易所交叉核验或商业展示许可核实。未知供应商证券字段明确提示待核验，不默认通过独立证券验证。
测试：`.venv/Scripts/python.exe -m pytest tests/test_evidence_quality.py -q`。使用 Mock，不调用真实模型或金融数据。历史报告不自动重写，请新建研究查看质量检查。
