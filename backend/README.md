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
