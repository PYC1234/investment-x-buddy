# Investment X Buddy — AI 开发与验证记录

更新日期：2026-10-10（Asia/Shanghai）

本文根据项目内已有记录、当前源码和本次实际执行结果整理。它说明 AI 如何参与，不把 AI 生成代码等同于人工验收，也不补写不存在的人工决策。

## 任务拆分与优先级

用户将紧急交付拆成多个有明确文件边界的阶段：

1. Stage 0：环境、金融数据来源、风险和公开文档审计，不开发产品。
2. Stage 0.5：配置 DeepSeek，并用三个最小请求验证文本、JSON Output 和 Tool Calling。
3. Stage 1A：只开发 `frontend/`，先交付高完成度研究工作台和 Demo 状态机。
4. 后端阶段：只开发 `backend/`，实现 FastAPI Agent Harness、SQLite 和测试。
5. Stage 3：另一个窗口负责前后端联调。
6. 本阶段：本窗口只整理 `docs/`、根 README 和提交清单，不改应用代码或执行部署。

优先级始终围绕可提交主链路：研究目标 → 计划 → 审批 → 执行 → Evidence → Report；真实金融数据、多租户和复杂基础设施排在主链路之后。

## AI 工具如何参与

记录中明确使用 Codex 完成以下工作：

- 读取需求并维护阶段边界，避免并行窗口修改相同目录。
- 审计本机 Node、Python、Git、网络和可选部署工具状态。
- 阅读公开的 DeepSeek、Next.js、FastAPI、金融数据和部署文档。
- 生成并修改 Next.js/TypeScript 前端、FastAPI/Python 后端及测试。
- 执行类型检查、Lint、构建、状态机测试和浏览器交互检查。
- 检查后端源码、接口、测试覆盖范围和部署配置，生成本组提交文档。

AI 没有创建 GitHub 仓库、提交或推送代码，也没有部署云服务。Stage 0 的金融 API/MCP 调用数为 0；Stage 0.5 的虚拟工具没有执行。

## 关键产品选择

### 为什么采用轻量 Harness

当前代码使用 FastAPI 服务层、显式状态、Tool Registry 和 SQLite，而没有引入大型 Agent 编排框架。这样可以在紧急交付范围内直接看到：计划如何验证、工具为何可调用、审批绑定什么版本、何时停止、Evidence 怎样进入 Report，以及失败后从哪里恢复。

源码中的 Harness 具有明确边界：Planner 生成结构化计划；Registry 校验工具和参数；RunService 管理审批、执行、事件和检查点；SQLite 保存状态。这比隐藏在框架内部的自动循环更便于作品审查。

### 为什么使用显式审批

投资研究涉及外部数据、成本和结论责任。后端让新 Run 停在 `PENDING_APPROVAL`，审批同时绑定 `plan_version` 和 `allowed_tools`。旧版本审批、未知工具或授权范围不足都会失败。这一设计使用户在执行前看见计划和工具范围，也限制 Planner 越权。

### 为什么要求 Evidence 引用

研究结论必须能回到工具输出。后端把每次成功工具结果保存为 Evidence，并让确定性 Report 的 Finding 引用 Evidence ID。工具缺失、调用失败或停止规则触发时，报告写入 `missing_information`，避免把没有数据的任务包装成正常结论。

### 为什么 Fixture 必须标记

当前三个金融工具都使用人工 Fixture。源码在 Tool Registry Schema、工具结果、Evidence 和 Report 中写入 `FIXTURE / DEMO DATA` 或 `is_demo`。前端也显示 DEMO DATA 横幅。这样可以演示 Agent 结构而不把构造数值冒充贵州茅台或其他公司的实时数据。

## 已记录的验证

### Stage 0 环境与安全审计

- 记录了 Windows 11、PowerShell 7.6.5、Node 24.8.0、npm 11.6.0、Python 3.12.0、pip 25.3 和 Git 2.50.1。
- 验证了指定公开站点的 DNS/HTTPS 可达性；没有验证供应商账户权限。
- 只检查环境变量是否存在，不输出 Key 值。
- 没有安装依赖、初始化仓库、连接数据库或调用金融 API。

### Stage 0.5 DeepSeek 最小验证

用户配置本地 Secret 并明确批准三个最小付费请求。执行时使用 `deepseek-flash`、官方 Base URL、60 秒超时和 `max_retries=0`：

| 测试 | 结果 | 请求 | 时延 | Token（输入/输出/总计） |
|---|---|---:|---:|---:|
| 基础文本生成 | PASS | 1 | 2659.6 ms | 13 / 24 / 37 |
| JSON Output | PASS | 1 | 898.3 ms | 117 / 96 / 213 |
| Tool Calling | PASS | 1 | 496.1 ms | 372 / 63 / 435 |
| 合计 | PASS | 3 | 4054.0 ms | 502 / 183 / 685 |

JSON 结果经过本地字段和类型校验；Tool Calling 验证了函数名和参数 JSON。没有执行虚拟 `get_stock_price`，也没有访问金融 API。完整记录见 `stage-0.5-verification.md`。

### 前端记录

前端开发阶段实际记录为：

- `npm install` 成功。
- `tsc --noEmit` / `npm run typecheck` 通过。
- `npm run lint` 通过。
- `npm run build` 通过，首页静态预渲染成功。
- 本地 Demo 状态机测试通过。
- 浏览器检查覆盖 1440px 桌面和 390px 窄屏。
- 实际点击 Plan、批准、Trace 和 Evidence 详情；状态按预期更新。
- 浏览器控制台 error/warn 检查结果为空。

这些是当时前端版本的自动化/浏览器记录。Stage 3 会继续修改前端，因此最终提交前必须重跑，不能直接视为最新联调版本已通过。

### 后端记录

当前源码包含 Pytest 用例，目标覆盖：

- 创建 Run、审批、执行、Evidence 和 Report 主链路
- 未审批执行阻断和工具参数校验
- 重试、模拟失败和 `PARTIAL`
- Checkpoint、重启读取和 Resume 不重复已完成 Task
- Context Compression、Memory、成本/停止规则
- CORS、有限 SSE 演示和错误脱敏

本次文档整理没有运行 Pytest，也没有找到可引用的最新通过数量。因此这里只记录“测试代码存在及其覆盖目标”，不声明当前提交的后端测试已经通过。

## AI 结果的修正与约束

已有记录中可确认的修正包括：

- Stage 0 的 PowerShell 管道语法错误在命令未执行后被改正。
- 沙箱无法访问系统服务和网络时，改用授权的只读宿主检查，没有把沙箱失败解释为机器不可用。
- DeepSeek 文档显示旧模型状态变化后，最终由用户把模型明确改为 `deepseek-flash`，实际响应也返回该模型。
- JSON 测试被描述为 JSON mode 加本地校验，没有夸大为服务端严格 JSON Schema。
- 前端遇到 Windows 沙箱内 Turbopack 路径权限错误后，使用授权构建重跑成功，并保留真实原因。
- 提交文档发现后端 CORS 只允许 `GET`、`OPTIONS`，将研究流程所需 `POST` 标为部署阻断项，没有越过窗口边界修改后端。

没有记录证明某位人工审阅者逐行审查了 AI 代码，因此本文不声称完成了人工代码审计。

## 仍待人工验收

- Stage 3 最终前后端字段映射、审批 Body、轮询和刷新恢复。
- 在本地真实 API 模式完成创建—计划—审批—执行—Evidence—Report。
- 后端最新 Pytest、前端最新 build/lint/typecheck 的最终重跑结果。
- CORS 的 `POST` 预检与生产 Origin 配置。
- DeepSeek Planner 在完整产品链路中的行为、成本和错误恢复。
- 云端 SQLite 持久磁盘、实例重启和数据恢复。
- Vercel/Render/Railway 实际部署、公开访问和未登录浏览器验收。
- 金融 Fixture 标识、报告措辞和不构成投资建议提示的人工合规检查。
- GitHub 仓库中 Secret、数据库文件、受限数据和许可证的最终检查。

## 事实边界

- 当前没有公开 Web URL 或 GitHub URL。
- 实时金融数据未接通；Fixture 数值不能用于投资判断。
- DeepSeek 的三次最小请求已验证协议能力，不等同于完整 Agent 研究质量验证。
- AI 生成和自动检查只能作为开发证据，最终提交仍需要用户完成部署、端到端操作和人工验收。
