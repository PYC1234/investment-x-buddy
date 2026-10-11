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

- Live financial data providers
- Authentication, tenant isolation, or user accounts
- Distributed worker queue and cross-process cancellation guarantees
- Live SSE streaming for persisted run events
- Automatic cloud disk provisioning or PostgreSQL migration
- LLM-written report prose; reports are deterministic and evidence-safe



## 扶摇真实数据模式
Render Environment 配置 `FUYAO_API_KEY`，部署本版本并重启后，工具自动使用扶摇真实只读接口。`PLANNER_MODE=fixture` 可继续保留：仅计划使用固定模板，金融证据使用真实接口，不调用收费 DeepSeek。
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
