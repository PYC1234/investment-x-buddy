# Investment X Buddy — Stage 0 数据源审计

审计日期：2026-10-10（Asia/Shanghai）。结论：扶摇四类核心数据在官方文档有明确契约；iFinD 有公开 MCP 接入与能力说明；本次没有金融业务 API、MCP 握手/工具发现或 LLM 推理调用。所有文档示例仅用于理解结构，不是本次取得的数据。

## 状态定义

- VERIFIED：已完成实际只读调用并检查对应结果。
- DOCUMENTED：官方文档明确存在，未完成实际调用。
- BLOCKED：当前缺少凭证、权限、连接信息或网络条件，不能验证。
- UNAVAILABLE：已明确确认在对应范围不可用。
- UNKNOWN：证据不足，不能判断。

每项分“能力证据状态”和“本次调用状态”，避免把有文档与可调用混淆。本报告无任何数据能力标记为 VERIFIED。

## 一、扶摇（优先数据源）

### 认证与访问条件

API Base URL 为 https://fuyao.aicubes.cn，REST 路径以 /api/ 开始。使用同花顺账号登录官方站点后签发账号绑定 API Key，通过 X-api-key 请求头认证；密钥仍需具有相应 capability 权限。文档给出 2001（缺少/无效密钥）、2003（权限不足）。MCP 复用 API Key，快速开始提到 API_KEY 环境变量。见[官方快速开始](https://fuyao.aicubes.cn/docs/quickstart/)。

本次在常见变量、官方变量 API_KEY 及 MARKETDB_API_KEY 等名称下均未发现配置，不读取登录态，不签发密钥，不发起匿名业务探测。认证与数据调用状态 BLOCKED。

### 内部能力与实际接口映射

所有端点均为 GET，认证均为 X-api-key + 对应 capability 权限。

| 内部能力 | 实际 REST 接口 / MCP 工具名 | 认证要求 | 关键参数 | 关键返回字段 | 能力证据状态 | 本次调用状态 |
|---|---|---|---|---|---|---|
| get_market_data | /api/a-share/prices/snapshot；get_a_share_prices_snapshot | 上述认证 | thscodes（逗号分隔）；省略时 limit/offset 分页 | data.timestamp、total、item[]；thscode、ticker、last_price、price_change、price_change_ratio_pct、open_price、high_price、low_price、prev_price、volume、turnover | DOCUMENTED | BLOCKED：无凭证 |
| get_price_history | /api/a-share/prices/historical；get_a_share_prices_historical | 上述认证 | 单个 thscode、interval=1d、start/end 毫秒戳；adjust=none/forward/backward | data.timestamp、item[].date_ms、open_price、high_price、low_price、close_price、volume、turnover | DOCUMENTED（日线） | BLOCKED：无凭证 |
| get_financial_data：利润表 | /api/a-share/financials/income-statements；get_a_share_financials_income_statements | 上述认证 | 单个 thscode、period=annual/quarterly；limit 或 start+end | report_date_ms、period_end_ms、currency、operating_income、net_profit、parent_holder_net_profit、basic_eps 等 | DOCUMENTED | BLOCKED：无凭证 |
| get_financial_data：资产负债表 | /api/a-share/financials/balance-sheets；get_a_share_financials_balance_sheets | 上述认证 | 同利润表 | assets_total、total_current_assets、non_current_nets_total、cash、accounts_receivable、total_debt、holder_equity_total | DOCUMENTED | BLOCKED：无凭证 |
| get_financial_data：现金流量表 | /api/a-share/financials/cash-flow-statements；get_a_share_financials_cash_flow_statements | 上述认证 | 同利润表 | act_cash_flow_net、invest_cash_flow_net、financing_cash_flow_net、pay_fixed_assets_etc_cash、cash_equivalents_net_addition 等 | DOCUMENTED | BLOCKED：无凭证 |
| get_valuation_data | /api/a-share/valuations/snapshot；get_a_share_valuations_snapshot | 上述认证 | 必填 thscodes，默认最多 100 个原始 token | data.timestamp、total、item[].thscode、ticker、name、pe_ttm、pe_mrq、pb_mrq、ps_ttm、pcf_ttm | DOCUMENTED（最新快照） | BLOCKED：无凭证 |

来源：[行情与历史 K 线](https://fuyao.aicubes.cn/docs/api-reference/prices/)、[财务报表](https://fuyao.aicubes.cn/docs/api-reference/financials/)、[估值](https://fuyao.aicubes.cn/docs/api-reference/valuations/)。内部工具名称由项目定义，并非供应商接口原名。

### 契约、单位与数据质量边界

行情：价格/成交额为 CNY，成交量为股，涨跌幅为百分比数值（1.74 即 1.74%），时间戳为毫秒；快照不返回中文名，需要独立标的检索。历史每次一个标的、时间窗不超过十年，默认前复权。介绍页写日/周/月，详情页明确当前仅 1d；因此周/月原生支持记 UNKNOWN，不能承诺。

财务：合并报表，annual/quarterly，最近 N 期默认 4、范围 1–20；limit 与 start/end 互斥，区间须成对且最多十年。金额原币元，EPS 元/股，空值不补零。报告期末与披露日期不同；季度字段不自动等价于单季度流量，累计/单季口径需要样本核实。data.timestamp 在该接口取报告期末最大值，不能当作抓取时刻。见[财务契约](https://fuyao.aicubes.cn/docs/api-reference/financials/)。

估值：五个比率按倍数解读，保留 TTM/MRQ、负值与 null；时间戳是上游元数据最大有效时间，不代表所有指标同步。只提供最新快照；本端点“历史估值”记 UNAVAILABLE（文档明确不提供），不能推广为供应商全部产品都无此能力。见[估值契约](https://fuyao.aicubes.cn/docs/api-reference/valuations/)。

统一响应包含 code/message/request_id/data。HTTP 200 仍可能是业务错误；须检查 code=0、结构、非空记录及数据日期。总览明确 HTTP 429 或 code=4001 均可表示限流，优先于部分页面“HTTP 恒为 200”的简化表述。缺数、停牌/非交易日、超时与错误不能转成零值。见[接口总览](https://fuyao.aicubes.cn/docs/api-reference/overview/)。

### 配额、试用与数据展示许可

| 问题 | 状态 | 核实结果 |
|---|---|---|
| 调用总量 | DOCUMENTED | 官方目前声明不限制累计次数；会动态限流，未给固定保证 QPS |
| 限流处置 | DOCUMENTED | HTTP 429 / code=4001；降低并发、延迟后重试，不能立即密集重试 |
| 免费/测试 | UNKNOWN | 有登录、签发 Key 与在线调试入口；未找到明确免费定价/试用期限承诺，不能推断永久免费 |
| 当前账号额度/权限 | BLOCKED | 无配置凭证，未查询账户 |
| 项目使用与展示 | UNKNOWN（许可范围） | 产品介绍面向 AI Agent、投研和前端图表，说明用途匹配；没有核实完整数据许可、再分发、公开演示、缓存或第三方模型处理条款 |
| 商业使用/公开原始数据 | UNKNOWN | 需用户向供应商确认，不把文档公开或 Key 可申请当作授权 |

参考：[限流总览](https://fuyao.aicubes.cn/docs/api-reference/overview/)、[产品介绍](https://fuyao.aicubes.cn/docs/introduction/)、[文档索引](https://fuyao.aicubes.cn/llms.txt)。

后续最小验证建议（本次未执行）：单个 A 股快照一次、短窗口日线一次、最近一期利润表一次、估值快照一次；若产品需要全部三表，再分别验证另两表。对每一端点独立记录耗时、业务码、字段、单位、时间语义和脱敏 request_id，不因一个成功就把全部能力升级为 VERIFIED。调用前先确认合法权限及费用条件。

## 二、iFinD MCP（可选）

通过真实浏览器阅读公开动态页面，未登录，未使用 Cookie 或密钥。官网 HTML 200 与 MCP 连通性是两件事。

| 检查项 | 状态 | 证据和限制 |
|---|---|---|
| 服务接入流程 | DOCUMENTED | 使用指南说明个人中心 → MCP → 选择数据范围 → 生成客户端 JSON 配置 |
| 账号认证 | DOCUMENTED | 支持同花顺 APP 账号或 iFinD 账号；个人中心“密钥”取得 MCP 密钥 |
| 标准连接说明 | DOCUMENTED | 提供 Cursor、Trae、CherryStudio 等客户端接入教程，Cursor 指南说明配置后可查看工具列表及描述 |
| 实际地址/传输/认证参数 | BLOCKED | 个人配置需登录生成；本次未取得服务 endpoint、headers 或 URL 参数，不能把官网首页当作 MCP endpoint，也不能猜测 SSE/Streamable HTTP |
| 工具发现支持 | DOCUMENTED | 官方说明客户端展示工具列表；本次未发送 initialize/notifications/initialized/tools/list |
| 实际 MCP 握手和 tools/list | BLOCKED | 无合法密钥和所选服务配置 |
| Python 后端集成 | DOCUMENTED（协议层）/UNKNOWN（该服务实测） | MCP 官方有 Python SDK，可构建远程客户端；推断技术上可接入，需匹配供应商实际 transport/auth 并实测。当前 Python 无 mcp 包，本阶段未安装 |
| A 股行情、日频数据、财务 | DOCUMENTED | 数据范围页明确列出；实际字段、单位、工具 schema 及账号权限未发现/验证 |
| 估值 | DOCUMENTED（概括能力） | 首页研究场景及指数板块等覆盖估值；A 股所需五项字段的具体工具契约 UNKNOWN |
| 新闻、公告 | DOCUMENTED | 范围页说明公告/财经新闻/热点事件语义搜索、相关段落返回 |
| 宏观 | DOCUMENTED | 覆盖中国/世界/区域/行业经济、利率、大宗等；指标时效和历史范围待验证 |
| 资金工具 | UNKNOWN | 当前公开页面未核实明确工具名及 schema；不能从“全部指标”推定某个资金接口存在 |
| 市场宽度工具 | UNKNOWN | 未确认专用广度工具；即使将来可用成分行情推导，也属于内部派生能力而非已发现的供应商工具 |
| 数据再分发/公开展示许可 | UNKNOWN | 未取得完整会员协议或企业数据授权范围；购买套餐不自动等于允许公开转发 |

来源：[前置准备](https://mcp.51ifind.com/#/docs/guide-prepare)、[Cursor 指南](https://mcp.51ifind.com/#/docs/guide-client-cursor)、[数据范围](https://mcp.51ifind.com/#/domains)、[FAQ](https://mcp.51ifind.com/#/docs/guide-faq)、[官方 MCP SDK](https://modelcontextprotocol.io/docs/sdk)。页面实际访问 URL 含站点自动追加的 syncCookieTimes 参数；报告使用无该非敏感导航参数的同一 hash 路由。

公开[个人订阅页](https://mcp.51ifind.com/#/pricing)当前显示免费体验总量 2,000 次、2 次/秒；基础/专业/旗舰月卡分别 40/99/199 元，对应 3,000/8,000/20,000 次/月。基础版不提供实时数据通道；宏观搜索另有限额，三档分别 20/200/500 次/月。当前页把付费额度旁的 5 标为“并发”，[2026-09-23 公告](https://mcp.51ifind.com/#/documents/changelog-2026-09-23-price-adjustment)标为“5 次/秒”，两者语义有差异，需供应商确认。实际权益以账户为准，本次未开通试用或购买。

FAQ 说明计次依赖实际工具请求数量，不等同于用户提问数；目前工具每次调用消耗一次额度。新工具/升级功能未来计费可能不同。这些是文档说明，未检查账单。iFinD 不必成为 Stage 1 的硬依赖，可在扶摇核心链路成立后追加。

## 三、LLM API

### 配置与授权结论

在环境审计列明的变量范围内，未发现 API Key、Base URL 或模型 ID；根目录无 .env*。不读取 Codex 登录配置，也不把当前 Codex 会话、CLI 或已安装 openai 2.15.0 当作项目模型 API 授权。

未选择、猜测或调用任何模型；推理调用次数为 0。当前没有可供批准的具体供应商/模型/请求预算，因此停止该项实际探测，并记录用户后续操作条件，而不是请求空泛批准。

| 能力 | 本项目当前状态 | 官方参考与后续验收条件（未执行） |
|---|---|---|
| 基础文本生成 | BLOCKED，待验证 | 配置合法目标后发送极短输入，检查成功响应和非空文本 |
| JSON 输出 | BLOCKED，待验证 | 分别确认 json_object 与严格 JSON Schema 支持情况；解析并校验 schema，合法 JSON 不等于严格结构化 |
| Tool/Function Calling | BLOCKED，待验证 | 声明不访问外部的只读示例工具；检查工具名、调用 ID、参数 JSON/schema；完成工具结果回传后的第二轮 |
| 多轮上下文 | BLOCKED，待验证 | 第二轮验证前轮事实或工具结果；使用供应商支持的 messages/会话机制 |
| Token 用量 | BLOCKED，待验证 | 检查 usage 中输入、输出、总 token；记录缓存/推理 token 是否单列，不能只用字符数当账单 |
| 超时/错误 | BLOCKED，待验证 | 确认客户端连接/读取/总超时；采集脱敏状态码和供应商错误字段；不故意压测 429 或消耗大额额度 |
| 模型价格 | UNKNOWN | OpenAI 有公开价格页，但目标供应商和模型未定，不能据此计算本项目价格或推定账户余额 |

OpenAI 官方有[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)、[工具调用](https://developers.openai.com/api/docs/guides/function-calling)、[错误码](https://developers.openai.com/api/docs/guides/error-codes)及[价格](https://developers.openai.com/api/docs/pricing)文档。它们证明 OpenAI 对相关机制有文档，不证明任何“OpenAI 兼容”供应商支持相同功能。

未来探测应先取得供应商、非敏感 Base URL、精确模型 ID、合法凭证及价格/费用上限；调用前向用户确认具体低成本方案（建议总计 3–4 个短请求并限制输出 token），得到批准后执行。不得在报告、截图、仓库或终端输出凭证或含凭证 URL。
