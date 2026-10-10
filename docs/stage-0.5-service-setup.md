# Investment X Buddy — Stage 0.5 DeepSeek 服务配置

更新日期：2026-10-10（Asia/Shanghai）

## 当前配置方案

| 配置项 | 当前值或来源 | 状态 |
|---|---|---|
| 服务商 | DeepSeek 官方 API | 已选定 |
| Base URL | `https://api.deepseek.com` | 已写入安全模板 |
| 模型 ID | `deepseek-flash` | 用户已选择；实际请求返回同一模型 ID |
| API Key | 仅由用户在本地配置 | 已检测为非空；未读取、打印或记录具体内容 |
| Python SDK | `openai 2.15.0` | Stage 0 已发现，无需安装 |

项目根目录现有两个配置文件：

- `.env.example` 是可提交的配置示例，只含变量名称、官方非敏感配置和安全占位符。
- `.env` 是本机私密配置，API Key 值当前留空，并已由 `.gitignore` 排除。

## 用户手动配置

使用 VS Code 在本机打开项目根目录的 `.env`，只修改这一行：

```dotenv
DEEPSEEK_API_KEY=你的真实密钥
```

不要把真实密钥粘贴到聊天窗口、文档、截图、终端输出或 `.env.example`。保存 `.env` 后，只需在聊天中回复“已配置，并批准执行三个最小测试”；不要附带密钥。

也可以只为当前 PowerShell 会话设置环境变量：

```powershell
$env:DEEPSEEK_API_KEY = Read-Host 'DeepSeek API Key'
$env:DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
$env:DEEPSEEK_MODEL = 'deepseek-flash'
```

这种方式不会把密钥写进项目文件，但关闭 PowerShell 后变量会消失。测试优先读取进程环境变量；没有时再读取项目根目录 `.env`。任何读取只用于构造请求，不打印或写入日志。

## 官方文档核实与兼容性风险

DeepSeek 官方 API 使用 OpenAI 兼容接口，官方 Base URL 是 `https://api.deepseek.com`。官方文档说明 JSON Output 使用 `response_format={"type":"json_object"}`，Tool Calling 的结果位于 `message.tool_calls`，Token 计数以响应 `usage` 为准。

截至本次审计日期，官方[变更日志](https://api-docs.deepseek.com/updates/)说明 `deepseek-chat` 已于 2026-07-24 停止使用；当前[模型与价格页](https://api-docs.deepseek.com/quick_start/pricing/)列出的模型是 `deepseek-flash` 和 `deepseek-v4-pro`。用户随后把项目模型明确改为 `deepseek-flash`，三次实际响应的模型 ID 也均为 `deepseek-flash`。测试没有切换或调用其他模型。

若 `.env` 中的 Base URL 不是官方地址，测试必须在发出请求前停止，并由用户明确说明第三方服务的实际 Base URL、模型 ID 与授权情况。不会自行猜测或把密钥发送到未知服务。

## 验证计划与成本边界

用户已明确批准并完成三个短请求，每项仅一次，SDK 自动重试设为 0：

1. 基础文本生成：短提示词，低输出上限，检查非空文本。
2. JSON 输出：启用 `json_object`，检查内容可被 JSON 解析且包含指定字段。
3. Tool Calling：定义虚拟 `get_stock_price` 函数，要求模型生成调用；检查真实 `tool_calls`、函数名和可解析参数，不执行工具、不访问金融 API。

每项已记录墙钟响应时间、HTTP/SDK 结果、模型返回 ID、输入/输出/总 Token 和脱敏错误。三个请求均成功，没有触发认证、余额、模型或工具支持停止条件。原始文本响应和密钥均未写入仓库；详细结构校验见 `stage-0.5-verification.md`。

参考资料：

- [DeepSeek 首次 API 调用](https://api-docs.deepseek.com/)
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek Token Usage](https://api-docs.deepseek.com/quick_start/token_usage/)
