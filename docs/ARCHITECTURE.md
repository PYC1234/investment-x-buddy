# Investment X Buddy 架构

## 设计目标

系统将投资研究拆成可审查、可停止、可追踪的步骤。模型负责规划，不直接越过审批调用任意工具；工具结果先成为 Evidence，报告只能引用已经保存的 Evidence，并明确缺失信息和 Fixture 标记。

## 主链路

```text
用户研究目标
   │
   ▼
Planner
   │  生成 ResearchPlan 与有序 Task
   ▼
Approval
   │  绑定 plan_version 和 allowed_tools
   ▼
Executor ─────→ Tool Registry
   │                 │
   │                 └─ 白名单、JSON Schema、Pydantic 参数校验
   ▼
Evidence
   │  保存 tool、task、data、is_demo、时间
   ▼
Report
      引用 evidence_ids，披露缺失数据和停止原因
```

### Planner

真实实现：后端提供 `DeepSeekPlanner` 和 `FixturePlanner`。DeepSeek Planner 请求 JSON 对象，并在落库前用 `ResearchPlan` 和 Tool Registry 验证工具名与参数。Fixture Planner 生成固定的三步研究计划。

边界：模型只规划。当前没有让模型直接执行工具，也没有用模型撰写最终报告；DeepSeek 规划到前端展示的 Stage 3 全链路仍待验收。

### Approval

真实实现：Run 创建后进入 `PENDING_APPROVAL`。批准请求必须携带当前 `plan_version` 和完整 `allowed_tools`；版本不匹配、工具未注册或授权范围不足都会被拒绝。后端另有 reject 接口。

这样可以防止旧批准复用于新计划，也避免 Planner 生成的未知工具被静默执行。

### Executor 与 Tool Registry

真实实现：Executor 只运行已注册、已批准且参数验证通过的工具。每次尝试记录状态、耗时、结果或错误。目前三个工具均返回 Fixture：行情快照、盈利能力摘要和估值快照。

未实现：真实扶摇/iFinD 数据调用、分布式 worker、跨进程强取消和并行工具调度。

### Evidence 与 Report

真实实现：成功工具结果保存为 Evidence，并关联 Run、Task 和工具名。`is_demo` 与结果中的 `DEMO DATA` 标识用于防止 Fixture 被误认为实时行情。报告由确定性代码生成，Finding 包含 Evidence ID；缺失或失败任务进入 `missing_information`。

当前 Artifact 是 Report JSON 加前端报告视图。独立 Artifact 数据模型、文件导出和版本管理尚未实现。

## 状态与 Harness 机制

### Thread / Run / Task

- Thread：长期研究主题，保存标题和研究偏好，可以包含多个 Run。
- Run：一次规划、审批、执行和报告周期，具有版本、状态、用量和错误。
- Task：Run 内的有序步骤，保存工具、参数、状态、尝试次数和 Evidence ID。

Run 状态包括 `PLANNING`、`PENDING_APPROVAL`、`APPROVED`、`RUNNING`、`COMPLETE`、`PARTIAL`、`FAILED`、`REJECTED` 和 `CANCELLED`。

### Memory

真实实现：Thread 级键值 Memory 存在 SQLite 中；创建 Run 时可以保存 `research_preferences`，Planner 读取这些偏好。

边界：目前没有向量检索、语义记忆、用户身份隔离或记忆治理界面。前端 Demo Mode 的偏好只保存在页面会话。

### Context Compression

真实实现：保存检查点时，服务计算完整任务/Evidence 上下文的字符数，并保存仅包含状态、完成/失败 Task ID 和 Evidence ID 的摘要，同时记录 `before_chars` 和 `after_chars`。

边界：这是确定性摘要记录，不是模型级上下文窗口管理，也没有自动把摘要回填到多轮 LLM 对话。

### Checkpoint 与 Recovery

真实实现：规划完成、执行步骤、拒绝、取消和完成时写入顺序检查点。Resume 会读取已有状态，跳过已完成和已失败 Task，并将中断的 `RUNNING` Task 复位后继续。

边界：当前恢复依赖同一 SQLite 数据库；没有跨区域容灾或队列任务重建。

### Event Trace

真实实现：Run 创建、计划生成/失败、审批、执行、工具成功/失败、检查点、恢复和完成均写入事件表。前端 Trace 视图也支持本地演示事件。

未实现：持久化 Run 事件的实时 SSE。现有 `/events/demo` 只是有限演示流。

### Stop Rules

真实实现：后端限制工具调用数、执行轮数、单 Run 总时限和工具重试次数；用户可取消非终态 Run。停止后生成 `PARTIAL` 报告并披露原因。

边界：当前同步执行使跨进程取消保证有限；生产系统需要任务队列、租约和分布式取消。

## 持久化与接口

SQLite 保存 threads、runs、tasks、events、evidence、tool_calls、checkpoints 和 memories。FastAPI 暴露 Run 生命周期、Evidence、Report、Task、Checkpoint、Tool Call、Memory、Thread、Tool Registry、健康检查和非敏感能力配置接口。

前端请求集中在 API Adapter。Stage 3 正在对齐响应字段、审批请求和轮询状态；联调完成前，不能把前后端分别可运行等同于完整链路已通过。

## 安全与产品边界

- API Key 只在后端环境变量中，不能写入 `NEXT_PUBLIC_*`。
- CORS 使用明确 Origin 列表，不采用通配符。
- 错误响应避免回显提交值和秘密。
- 当前没有鉴权，公开部署只能用于无敏感数据的作品演示。
- 所有金融工具仍是 Fixture，不输出确定性涨跌预测、收益承诺或交易指令。
