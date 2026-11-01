# Agent 执行与研究闭环升级

本次实现使用现有 FastAPI、SQLite、工具白名单和审批机制，不依赖新增 Agent 框架。以下描述是代码能力，不能替代真实金融数据接入验证和生产验收。

## 已实现

1. **持久化后台执行**：审批与入队同一事务提交；HTTP 请求返回后 Worker 继续执行。SQLite 队列保存租约、心跳、重试范围和状态，进程重启后可领取排队或租约已过期的任务。
2. **并发和依赖**：计划支持 `task_key`、`depends_on`、子问题、证据要求、完成标准。拒绝循环、前向和未知依赖；独立任务按受限并发执行，失败依赖阻断下游。
3. **调用保护**：外部调用前持久化 STARTED 记录，累计调用预算不随重试/重启重置；取消或租约失效后旧 Worker 不再提交结果。工具仍是只读操作。
4. **真实事件流**：`GET /api/v1/runs/{id}/events/stream` 返回实际研究事件。支持 `after_id` 与 `Last-Event-ID`；沿用 Bearer 身份与研究归属校验。前端使用带鉴权的 fetch stream，轮询作为降级。
5. **结构化模型规划**：规划器接收实际工具说明、参数契约和资料版本，输出依赖图和验收标准；校验证券和工具参数。无效输出最多修复一次，合并两次成功响应返回的 token 用量。连续失败明确返回错误，不伪装为模型成功。
6. **研究覆盖检查**：分别检查盈利、估值、风险和综合研究所需证据类别。执行完成与研究覆盖状态独立展示。仅检查类别，不声称事实已核验。
7. **有限补充规划**：存在已导入且尚未查询的资料时，生成新版本计划，清空旧审批，保留成功证据。用户批准新版后才执行新增任务。默认最多 2 轮，总任务不超过 8，沿用总调用和运行时间预算。稍后导入资料时可点击“检查可补充资料”。
8. **新增资料工具**：历史估值、同业估值、资产负债表、现金流量表、公告/财报关键词检索。来源为部署者显式导入的公开资料包；不猜测供应商端点，不以股价推算或伪造历史 PE，不把未配置的工具宣传为实时数据服务。
9. **报告字段校验**：保留证据字段路径、数值、单位、口径与计算公式；校验引用、字段和确定性计算，过滤无法复核的显式 claim。自然语言推断标为未独立验证，检查通过不等于结论真实或适合投资决策。
10. **离线评测**：固定问题集覆盖意图、标的冲突、缺数据、失败、预算和恶意指令。通过 Fixture 回放运行，不使用真实 API 密钥，不产生模型或数据调用费用。另有并发、恢复、取消、补充审批、版本变化、报告篡改、SSE 和生命周期测试。

## 启动

从 `backend` 目录启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

默认 `EXECUTION_MODE=queued`、`WORKER_ENABLED=true`，API 生命周期启动一个 Worker。关闭页面不会停止研究；服务器重启需等待旧租约到期后恢复。

前端在另一个 PowerShell 中，从 `frontend` 目录运行。当前会话的 API 地址指向本地，保留已有 `.env.local` 文件：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8000'
npm run dev
```

访问 `http://127.0.0.1:3000`。若要验证公开部署，需重新构建并部署前后端；只更新本地源码不会改变 Netlify/Render 上的版本。

如需单独运行 Worker：在 API 进程配置 `WORKER_ENABLED=false`，另一个进程使用相同 SQLite 路径运行：

```powershell
.\.venv\Scripts\python.exe -m app.worker
```

`inline` 模式只用于小型本地回归测试。不要同时把多个主机的独立 SQLite 文件当作共享队列。

### 可配置项

| 配置 | 默认 | 说明 |
|---|---|---|
| `EXECUTION_MODE` | queued | queued / inline |
| `WORKER_ENABLED` | true | 是否在 API 内启动 Worker |
| `WORKER_POLL_SECONDS` | 0.5 | 队列轮询间隔 |
| `WORKER_LEASE_SECONDS` | 30 | 租约秒数，心跳为其三分之一 |
| `MAX_PARALLEL_TOOLS` | 3 | 独立工具并发数 |
| `MAX_SUPPLEMENT_ROUNDS` | 2 | 补充计划轮数，0 禁用自动补充 |
| `RESEARCH_DATA_DIR` | backend/data/research_sources | 仅存放可公开使用的资料包 |
| `MAX_TOOL_CALLS` | 8 | 累计外部调用预算 |
| `MAX_EXECUTION_ROUNDS` | 8 | 累计工具尝试上限 |
| `RUN_TIMEOUT_SECONDS` | 30 | 累计执行时间预算，不含等待审批时间 |
| `MAX_ACTIVE_RUNS_PER_USER` | 3 | 单身份待审批/规划/执行中的研究上限 |
| `MAX_RUN_REQUESTS_PER_HOUR` | 30 | 单身份每小时创建研究的请求上限 |

## 导入真实公开资料

资料契约见 [research-source-bundle.schema.json](research-source-bundle.schema.json)。空模板见 [research-source-bundle.example.json](research-source-bundle.example.json)。

每份文件绑定一只股票，各条记录必须包含 `source`（HTTP/HTTPS 原文地址）、`as_of`（资料时点）和 `basis`（口径）。财务数据单位固定为 CNY 元；财务期间不得晚于资料时点；资产=负债+权益必须满足允许误差。历史 PE/PB 直接来自可核验资料，不能从价格曲线编造。

```powershell
.\.venv\Scripts\python.exe -m app.import_sources .\public-sources.json
```

导入后会生成 `600519.SH.json` 这样的文件。工具参数绑定该文件 SHA-256，审批后文件发生任何变化都会拒绝执行，需新建计划。资料包是部署者管理的公开数据源，不是用户私有资料仓库；禁止放入密钥、个人财务或非公开文件。

公告检索是有来源/页码的关键词检索，不是已接入向量库的语义 RAG。未检索到相关原文时明确失败，不生成替代原文。

空模板不包含金融数据；本次没有新增真实供应商账户或自动下载任何财务资料。

## 测试与评测

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m app.evaluate --output ..\docs\agent-offline-evaluation.json
```

评测的 pass rate 仅代表这组离线规则回归通过比例，不能当作真实模型准确率、用户采用率或收益指标。模型规划路径另以 MockTransport 校验格式修复和计费汇总；尚需真实模型的独立灰度验收。

## 部署与运行边界

- SQLite 数据目录和 `RESEARCH_DATA_DIR` 必须在持久化磁盘上；使用同一份文件的单机 Worker 可通过租约互斥。跨主机扩容应改用共享数据库/队列，当前未实现分布式部署。
- 外部数据查询为 at-least-once：进程在请求成功但结果未落库时崩溃，恢复后可能再次发起只读查询。已落库成功任务不重复执行；不宣称外部接口 exactly-once。
- Python 线程中的同步请求无法被强制杀死。总时限/取消后结果被隔离不提交，底层请求仍可能到其自身超时才结束；因此工具必须保持只读且有供应商超时。
- 数据结构、来源 URL 和引用通过校验，不代表资料真实性、全文完整性、行业可比性或自然语言推断已被证明。
- 多项失败后保留成功证据；预算已耗尽时不会通过“恢复”重置预算。
- 运行时长按执行阶段与心跳累计；进程异常退出时额外计入最多一个心跳间隔的未知执行时间，不把等待租约过期的全部停机时间计作执行。调用预算在请求发出前独立记账。
- 未自动更新线上环境变量或部署；本地验证后需使用真实供应商和持久化环境做上线验收。
