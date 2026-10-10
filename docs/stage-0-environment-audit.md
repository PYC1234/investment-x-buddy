# Investment X Buddy — Stage 0 环境审计

审计日期：2026-10-10（Asia/Shanghai）  
工作目录：C:\Users\29248\Desktop\XBuddy  
范围：只读环境、网络、文档与可行性检查；仅创建本阶段四份 Markdown 文档。

## 结论与判定规则

基础开发环境具备，Stage 0 审计完成；真实数据、模型和数据库的集成就绪条件尚未通过。可在用户另行启动后进入 Stage 1 的架构与契约设计，但不能据此宣布端到端开发环境已就绪。若 Stage 1 包含真实 API 和持久化联调，应先解除相应阻塞。

PASS 表示该项检查实际通过；WARN 表示有条件满足或存在风险；FAIL 表示明确不满足该项必要条件；NOT_TESTED 表示未执行或缺少条件。可选 CLI 缺失不构成整体 FAIL。

## A. Windows 与开发工具

| 项目 | 检测结果、实际版本或状态 | 满足需求 | 风险与建议 |
|---|---|---|---|
| Windows | PASS：Windows 11 家庭版 中文版，10.0.26200，Build 26200，64 位/AMD64 | 是 | 原生 Windows 可开发；本阶段未验证生产 Linux 环境的依赖兼容性 |
| PowerShell | PASS：7.6.5，Core | 是 | 命令在此版本执行；未独立验证 Windows PowerShell 5.1 |
| VS Code CLI | PASS：1.141.0，x64；code 可调用 | 是 | 沙箱内出现 EPERM，宿主只读复核成功；不需要修改 PATH |
| Codex CLI | PASS/WARN：codex-cli 0.162.0-alpha.2 可返回版本 | 能执行版本检查 | 属于 alpha；启动有临时目录清理/PATH aliases 拒绝访问警告，不代表 CLI 不存在。未做模型调用 |
| Codex VS Code 扩展 | NOT_TESTED：默认 CLI 扩展清单、默认扩展目录均未发现 openai/codex 匹配项 | 无法确认扩展运行状态 | 其他 profile、远程环境或其他安装位置未检查。CLI 可用与扩展是否安装、登录、启用互不等价 |
| Git | PASS：2.50.1.windows.1 | 是 | 当前目录不是 Git 仓库；未执行初始化 |
| 当前 Git 仓库 | WARN：git rev-parse 返回 not a git repository | 不影响设计，影响版本管理 | 后续阶段由用户授权初始化/关联指定仓库；无可验证的当前远程仓库 |
| GitHub CLI | WARN：gh 未在当前 PATH 发现；认证状态 NOT_TESTED | 可选工具，不阻塞本地开发 | 未执行 gh auth status；GH_TOKEN/GITHUB_TOKEN 未检测到，也不能据此断言浏览器或 Git Credential Manager 未登录 |
| GitHub 远程权限 | NOT_TESTED：无指定仓库、无当前 Git 远程 | 未确认 | 官网 HTTP 200 不代表读写权限；后续针对用户指定仓库做只读权限核实 |
| Node.js | PASS：v24.8.0 | 满足所查 Next.js 最低 Node 20.9 要求 | 未安装前端依赖、未构建；不代表全部依赖已兼容。后续固定项目与云端运行时版本 |
| npm | PASS：11.6.0，npm --version 成功 | 是 | 未读取 npm 配置/认证信息；未验证 registry 下载 |
| Python | PASS：3.12.0 | 满足所查 FastAPI >=3.10 | 未运行 FastAPI 应用；后续选择并固定依赖版本 |
| pip | PASS：25.3，绑定 Python 3.12 | 是 | 仅版本检查，没有安装依赖 |
| venv | PASS（有限）：标准库导入、命令帮助成功，ensurepip 23.2.1 | 模块可用 | 未创建虚拟环境，创建及安装能力 NOT_TESTED |
| Python 依赖 | WARN：openai 2.15.0；fastapi、uvicorn、psycopg、psycopg2-binary、asyncpg、mcp 未发现 | 依赖未齐备，符合本阶段不安装要求 | 仅检查当前 python 的包元数据；其他 Python/虚拟环境未遍历 |
| PostgreSQL 客户端 | WARN：psql、pg_isready 未在 PATH 发现 | 本地客户端未就绪 | 可能存在非标准路径安装；云端数据库可替代本地服务 |
| PostgreSQL 服务 | WARN：宿主查询无名称匹配 postgres 的服务；标准安装目录不存在；5432 无监听 | 未发现可用本地实例 | 不排除其他端口、容器、WSL、远程或自定义服务名；不做“全机绝无 PostgreSQL”结论 |
| 数据库连接 | FAIL（持久化联调门槛）：未发现 DATABASE_URL 或所查 PG* 配置 | 尚不满足 | 用户选择现有本地/托管 PostgreSQL；后续授权只读连接测试。本阶段未连接、建库、建表 |
| Vercel/Railway/Render CLI | WARN：均未在 PATH 发现 | 可选 | 可使用网页/Git 集成部署；当前不安装 |
| Docker | WARN：未在 PATH 发现 | 可选 | 不是本方案必需项，不作为整体阻塞 |
| 工作目录 | PASS：初始只有 13_投资XBuddy.md（2688 字节）；四个目标文档不存在 | 可保存审计文件 | 使用 CreateNew 防止覆盖；实际成功写入报告作为写权限验证，不另外创建测试垃圾文件 |

原文件审计前 SHA256：1591815706D05571A748151E8FE4069360EF2042D7CD13544C1CBED1FAF91F3D。最终复核以 AI 开发记录及执行输出为准。

版本要求来源：[Next.js 安装要求](https://nextjs.org/docs/app/getting-started/installation)、[FastAPI 官方发行元数据](https://pypi.org/pypi/fastapi/json)。只核实最低运行时要求，未做框架安装与构建。

## B. 网络分层验证

执行方法：Resolve-DnsName；curl.exe GET，跟随重定向，连接超时 8 秒，总超时 15 秒，响应体丢弃，仅记录状态与耗时；未附带账号凭证、未读取 Cookie、未跳过 TLS 验证。

| 目标 | 本机 DNS | HTTPS/最终 HTTP | 单次耗时 | 文档/页面内容 | API 认证 | 业务调用 |
|---|---|---|---|---|---|---|
| https://fuyao.aicubes.cn/docs/ | PASS | PASS / 200，curl exit 0 | 0.437s | PASS；详细文档通过官方站点 GET 读取 | NOT_TESTED：缺少凭证 | NOT_TESTED |
| https://mcp.51ifind.com/?syncCookieTimes=1 | PASS | PASS / 200，curl exit 0 | 0.309s | PASS；HTML 为动态应用，浏览器已读取指南、范围、订阅页 | NOT_TESTED：缺少密钥/服务配置 | NOT_TESTED；无 MCP 握手 |
| https://github.com/ | PASS | PASS / 200，curl exit 0 | 0.713s | PASS：官网 HTTP；不等价于私有仓库访问 | NOT_TESTED | NOT_TESTED |
| https://vercel.com/ | PASS | PASS / 200，curl exit 0 | 2.358s | 官方部署/限制文档已读取 | NOT_TESTED | NOT_TESTED |
| https://railway.com/ | PASS | PASS / 200，curl exit 0 | 2.204s | 官方部署/价格/SSE 文档已读取 | NOT_TESTED | NOT_TESTED |

五项宿主 TLS 校验结果均为 0；结合 curl exit 0 与 HTTP 200 才判定 HTTPS 成功。这些是一次性网页访问观测，不能推导 SLA、数据时效、API 授权或生产云端出站可达性。

初次沙箱检查全部 DNS 失败、curl exit 6、HTTP 000；此时 TLS 根本没有建立，不能把 ssl_verify_result=0 当作成功。随后获准执行相同只读宿主检查并通过。因此该失败归因于受限执行上下文，不判定本机互联网故障。系统 CIM/服务查询同样在宿主复核通过。没有修改代理、证书、DNS、hosts 或防火墙。

HTTP_PROXY、HTTPS_PROXY、ALL_PROXY 在所查 Process/User/Machine 范围均未发现；没有读取系统代理值，不能断言系统完全没有代理。

## C. 配置检查边界

仅输出变量存在性，未打印值；在进程、用户、系统三个范围检查并复核：

- LLM：OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_API_BASE、OPENAI_MODEL、OPENAI_MODEL_ID、LLM_API_KEY、LLM_BASE_URL、LLM_MODEL、LLM_MODEL_ID。
- 金融：FUYAO_API_KEY、FUYAO_TOKEN、FUYAO_BASE_URL、IFIND_TOKEN、IFIND_API_KEY、IFIND_MCP_URL、API_KEY、MARKETDB_API_KEY、MARKETDB_API_BASE_URL、IFIND_MCP_KEY、IFIND_MCP_API_KEY。
- 补充模型变量：DEEPSEEK_API_KEY、DASHSCOPE_API_KEY、SILICONFLOW_API_KEY、AZURE_OPENAI_API_KEY、AZURE_OPENAI_ENDPOINT、MODEL_ID、MODEL_NAME、API_BASE_URL。
- 数据库：DATABASE_URL、PGHOST、PGPORT、PGDATABASE、PGUSER、PGPASSWORD。
- GitHub：GH_TOKEN、GITHUB_TOKEN。

以上均未检测到。工作区根目录没有 .env* 文件。没有读取用户凭证库、Codex 登录文件、浏览器 Cookie、其他项目的 .env 或完整敏感 URL；自定义变量名称/其他配置位置可能存在，故结论是“本次范围未发现”，不是“用户没有任何凭证”。

## D. 数据库与部署可行性

| 组件 | 评估 | 平台条件与风险 | 后续建议 |
|---|---|---|---|
| Next.js → Vercel | DOCUMENTED：官方支持 Next.js | Hobby 免费且限个人非商业用途；笔试公开展示是否符合具体条款需用户确认。账户、绑卡、部署授权未测试 | 前端独立部署；本阶段未创建项目 |
| FastAPI → Railway | DOCUMENTED：官方部署指南存在 | 支持长期运行服务；是否休眠取决于 Serverless 配置；试用账户可能限制出站访问 | Web API 与 Worker 使用独立服务/进程，固定运行时 |
| FastAPI → Render | DOCUMENTED：官方部署指南存在 | 免费 Web 无入站流量 15 分钟会休眠，唤醒约一分钟；不适合保证持续后台执行 | 演示可接受冷启动时可评估免费 Web；持续 Worker 需预算 |
| 独立 Worker | 架构建议，未实现/验证 | 审批等待、长研究、断开浏览器不应依赖单次 HTTP 请求生命周期；Render Background Worker 不在免费实例类型中 | 由独立 Worker 推进任务，检查点/事件/租约存 PostgreSQL，设计幂等与重启恢复；小型原型可共享代码，但执行生命周期要独立 |
| PostgreSQL | 本地未发现，云端方案 DOCUMENTED | Railway 有 PostgreSQL 服务方案；托管程度、备份责任应按方案核实。Render Free Postgres 1 GB、30 天到期，不能承担长期研究记忆 | 明确数据库区域、TLS、连接池、备份与有效期，再做只读 SELECT 1/version 测试 |
| Vercel SSE/代理 | 文档确认流式响应计入函数执行时间 | Fluid Compute Hobby 上限 300s；Pro/Enterprise 通用上限 800s（文档另列受条件约束的 Beta 更长时限）；不可假设长流无限 | 优先让前端直接连接后端 SSE，核实 CORS/认证与断线续传 |
| Railway SSE | DOCUMENTED | 官方说明普通 SSE 请求上限 15 分钟；无数据 5 分钟会关闭 | 定期心跳、event id、Last-Event-ID/游标补发与自动重连；任务不随 SSE 断开而取消 |
| Render SSE | DOCUMENTED：官方有 SSE 示例 | 本次未确认自建 Web SSE 的通用最大连接时长；平台任务事件 API 的限制不能套用到自建应用 | 云端实际部署后做长流与空闲连接测试 |
| 云端持久化 | 未创建资源、未实测 | Web 本地文件系统可能临时；重启后内存状态消失 | 长期记忆、审批、检查点、成本轨迹写入数据库；产物存储方案另行确认 |

费用快照（非账户报价）：Railway 文档列试用 30 天或用完一次性 5 美元，随后 Free 每月 1 美元额度；Hobby 每月最低 5 美元并包含 5 美元使用额度，超出按量计费；付费订阅文档要求后付费卡。Limited Trial 的出站限制可能阻断金融/LLM API。Render 免费 Web 每工作区每月 750 小时，免费数据库到期与备份限制需留意；支持未添加支付方式时暂停超额免费服务，但本账户注册/绑卡资格未验证。Vercel Hobby 为免费额度，Pro 升级涉及支付卡；是否触发账户风控或验证要求 UNKNOWN。

上述费用/限制可能变更，正式部署时以控制台和官方条款为准；本阶段没有购买或开通任何资源。

来源：
- [Vercel Next.js](https://vercel.com/docs/frameworks/full-stack/nextjs)、[Hobby](https://vercel.com/docs/plans/hobby)、[Functions 限制](https://vercel.com/docs/functions/limitations)
- [Railway FastAPI](https://docs.railway.com/guides/fastapi)、[价格](https://docs.railway.com/pricing/plans)、[试用](https://docs.railway.com/pricing/free-trial)、[Serverless](https://docs.railway.com/pricing/cost-control)、[SSE](https://docs.railway.com/guides/sse-vs-websockets)、[PostgreSQL](https://docs.railway.com/databases/postgresql)
- [Render FastAPI](https://render.com/docs/deploy-fastapi)、[免费限制](https://render.com/docs/free)、[Worker](https://render.com/docs/background-workers)、[SSE 示例](https://render.com/docs/deploy-go-gin)

## E. 下一阶段门槛

1. 用户提供选定 LLM 服务的非敏感供应商名称、Base URL 主机及模型 ID，并在本机安全配置密钥；确认价格和探测预算后再进行少量调用。
2. 用户通过扶摇官方账号取得所需 capability 的合法权限；确认使用/展示范围后，最少请求核实四类核心能力。
3. 选定现有或待用户开通的 PostgreSQL，完成只读连接验证。
4. 明确 Stage 1 是否只做架构设计；若要求联调，上述三项为前置条件。GitHub/云端授权可在部署前解决，iFinD 可延期。
5. 本阶段不自动安装依赖、初始化仓库或启动 Stage 1。
