# Investment X Buddy

Investment X Buddy 是面向个人投资研究者的 AI Agent 工作台。用户给出研究目标后，系统生成受控研究计划，在用户批准工具范围后执行任务，将数据整理为可追踪的 Evidence 和 Report，并记录成本、时延、检查点与失败状态。

> 当前状态：前端、FastAPI Harness、Fixture 主链路和本地前后端联调均已完成；云端部署与线上验收尚未完成。所有 Fixture 金融数值均为 **DEMO DATA**，不是实时行情或投资建议。

## 解决的问题

普通聊天式研究容易混淆计划、数据来源和模型结论。Investment X Buddy 把研究过程拆成可观察的对象：目标属于 Thread，单次尝试属于 Run，计划步骤属于 Task，工具结果保存为 Evidence，最终报告作为 Artifact 展示。用户可以在执行前审查计划和工具权限，并在失败后查看事件与恢复点。

## 主要功能

- 研究线程、新建研究目标和历史记录界面
- Planner 生成结构化任务计划，显式等待审批
- Tool Registry 白名单与 Pydantic 参数校验
- Fixture 工具执行、Evidence 引用和确定性报告
- 暂停展示、拒绝、取消、失败、重试、部分完成和恢复入口
- Token、估算成本、工具时延和事件轨迹
- SQLite 保存 Thread、Run、Task、Evidence、Tool Call、Checkpoint 和 Memory
- Demo Mode 与 FastAPI 模式的明确视觉区分
- PE、PB、ROE、价格和财务趋势可视化；Fixture 数据始终标为 DEMO DATA

## Agent Harness

```text
Research Goal
    ↓
Planner ──→ Plan + Tasks ──→ Human Approval
                                  ↓
Tool Registry ←── Executor ──→ Evidence ──→ Report
                    │              │
                    ├─ Events      ├─ source / demo label
                    ├─ Checkpoint  └─ missing information
                    ├─ Stop Rules
                    └─ Recovery
```

Harness 采用轻量、可审计的服务层，而不是复杂编排框架。Planner 只能选择注册工具；Approval 绑定计划版本和允许的工具集合；Executor 在工具调用次数、执行轮数、重试次数和总时限内运行。详细说明见 [架构文档](docs/ARCHITECTURE.md)。

## 核心对象关系

| 对象 | 含义 | 当前落地 |
|---|---|---|
| Thread | 持续研究主题和研究偏好 | SQLite；包含多个 Run |
| Run | 一次从规划到报告的执行 | 状态、计划版本、用量、错误和报告 |
| Task | Run 内的有序工具任务 | 参数、状态、尝试次数、Evidence ID |
| Evidence | 工具结果及其来源 | 与 Task/Run 关联；当前金融工具均为 Fixture |
| Artifact | 面向用户的研究成果 | 当前以 Report JSON 和前端报告视图呈现；未实现独立制品表或文件导出 |

## 技术栈

- 前端：Next.js App Router、TypeScript、Tailwind CSS、Recharts、Lucide、Radix UI
- 后端：FastAPI、Pydantic、HTTPX、SQLite
- Planner：DeepSeek JSON Planner；可切换 Fixture Planner
- 测试：Pytest、TypeScript、ESLint、Next.js production build、浏览器交互检查

## 目录

```text
XBuddy/
├─ frontend/              # Next.js 研究工作台
├─ backend/               # FastAPI Harness、SQLite 与测试
├─ docs/                  # 架构、部署、AI 开发与审计记录
├─ README.md
└─ SUBMISSION.md
```

## 本地运行

### 后端（PowerShell）

```powershell
Set-Location C:\Users\29248\Desktop\XBuddy\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

健康检查：`http://127.0.0.1:8000/api/v1/health`；OpenAPI：`http://127.0.0.1:8000/docs`。

### 前端（另一个 PowerShell）

```powershell
Set-Location C:\Users\29248\Desktop\XBuddy\frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

访问 `http://127.0.0.1:3000`。

## 环境变量

公开仓库只提交变量名和安全示例，不提交真实密钥。

| 变量 | 位置 | 用途 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | 前端 | FastAPI 公网或本地 Origin；不能放 API Key |
| `PLANNER_MODE` | 后端 | `fixture` 或 `deepseek` |
| `DEEPSEEK_API_KEY` | 后端秘密 | DeepSeek 认证 |
| `DEEPSEEK_BASE_URL` | 后端 | DeepSeek API Origin |
| `DEEPSEEK_MODEL` | 后端 | 模型 ID |
| `CORS_ORIGINS` | 后端 | 允许的前端 Origin JSON 数组 |
| `SQLITE_PATH` | 后端 | SQLite 文件路径 |
| `MAX_TOOL_CALLS`、`MAX_EXECUTION_ROUNDS`、`MAX_TOOL_RETRIES`、`RUN_TIMEOUT_SECONDS` | 后端 | 停止规则 |
| `DEEPSEEK_INPUT_COST_PER_1M`、`DEEPSEEK_OUTPUT_COST_PER_1M` | 后端 | 可选成本估算 |

`FUYAO_API_KEY` 和 `DATABASE_URL` 已作为配置入口保留，但实时金融数据和外部数据库尚未接入主链路。

## Demo Mode 与真实 API 模式

| | Demo Mode | FastAPI 模式 |
|---|---|---|
| 计划 | 前端本地状态机或后端 Fixture Planner | FastAPI；可配置 DeepSeek Planner |
| 金融数据 | 本地/后端 Fixture，强制标记 DEMO DATA | 当前工具仍是 Fixture；实时金融供应商未接通 |
| 持久化 | 前端会话状态 | 后端 SQLite |
| Evidence / Report | 演示视图 | FastAPI Evidence 与确定性 Report 接口 |
| 适用范围 | 展示 UI 和失败恢复交互 | Harness 联调与后端行为验证 |

即使使用 DeepSeek Planner，当前金融工具结果仍是 Fixture，不能称为真实市场研究。

## 测试状态

- 已记录通过：DeepSeek 基础文本、JSON Output、Tool Calling 三次最小验证，共 685 Token；虚拟金融工具未执行。详见 `docs/stage-0.5-verification.md`。
- 已记录通过：前端 TypeScript、ESLint、production build、Demo 状态机；浏览器检查覆盖 1440px、390px、审批、Trace、Evidence 弹窗和控制台错误检查。
- 已记录通过：Stage 3 前端 typecheck、lint、production build，后端 Pytest 11 项；Fixture Planner 的创建—审批—执行—Evidence—Report、事件和刷新恢复已完成本地端到端验证。
- 待验证：DeepSeek Planner 的云端全链路、Netlify/Render 部署和线上持久化。

## 已实现与未实现

已实现：结构化规划、显式审批、注册工具白名单、Fixture 执行、Evidence、确定性报告、事件轨迹、成本/时延字段、SQLite Memory/Checkpoint、失败与 PARTIAL 路径、响应式工作台。

未实现或待验收：实时金融数据、鉴权与多租户、分布式任务队列、持久化事件的实时 SSE、PostgreSQL 迁移、独立 Artifact 存储/导出，以及线上部署与验收。

## 部署

前端计划部署到 Netlify，后端部署到 Render。仓库根目录的 `netlify.toml` 已将 Base Directory 设为 `frontend`，使用 `npm run build` 构建并发布 `.next`。Render 未上线时不配置 `NEXT_PUBLIC_API_BASE_URL`，前端保持 Demo Mode；后端上线后在 Netlify 构建环境中设置该公开 Origin 并重新部署。SQLite 只有在挂载持久磁盘并正确设置 `SQLITE_PATH` 时才能跨重启保留；演示部署应使用单个 Uvicorn worker。完整步骤和验收清单见 [部署文档](docs/DEPLOYMENT.md)。当前没有公开 Web URL，也没有声称部署完成。
