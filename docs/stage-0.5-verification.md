# Investment X Buddy — Stage 0.5 LLM 能力验证

更新日期：2026-10-10（Asia/Shanghai）

## 当前结论

用户已在本地 `.env` 配置凭证，选择 `deepseek-flash`，并明确授权三个最小测试。2026-10-10 通过 DeepSeek 官方 Base URL 执行完毕：三个测试均为 **PASS**，每项恰好一次请求，总请求数为 **3**，SDK 自动重试显式设为 0。

| 测试 | 状态 | 请求模型 / 响应模型 | 实际请求数 | 响应时间 | 输入 Token | 输出 Token | 总 Token | 错误信息 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 基础文本生成 | PASS | `deepseek-flash` / `deepseek-flash` | 1 | 2659.6 ms | 13 | 24 | 37 | 无 |
| JSON 结构化输出 | PASS | `deepseek-flash` / `deepseek-flash` | 1 | 898.3 ms | 117 | 96 | 213 | 无 |
| Tool Calling / `get_stock_price` | PASS | `deepseek-flash` / `deepseek-flash` | 1 | 496.1 ms | 372 | 63 | 435 | 无 |
| **合计** | **PASS** | — | **3** | **4054.0 ms** | **502** | **183** | **685** | **无** |

响应时间为客户端墙钟时间，包含网络与服务端处理时间，只代表本次单点样本，不构成延迟 SLA。Token 直接取自每次 API 响应的 `usage`。

## 实际结构校验结果

### 基础文本生成：PASS

- HTTP/SDK 请求成功，`finish_reason=stop`。
- assistant 文本非空，字符数 42。
- 返回 Token 用量：输入 13、输出 24、合计 37。
- 没有保存完整回答文本，避免把与验证无关的模型内容写入仓库。

### JSON 输出：PASS（JSON mode）

- 使用 `response_format={"type":"json_object"}`；提示明确要求只输出 JSON。
- `json.loads` 完整解析成功，证明没有 JSON 前后的无关文本。
- 顶层字段集合严格等于 `research_goal`、`symbol`、`tasks`、`required_tools`，没有额外顶层字段。
- `research_goal` 与 `symbol` 为字符串；`tasks` 与 `required_tools` 为字符串数组。
- `finish_reason=stop`；输入 117、输出 96、合计 213 Token。
- 本次验证的是 JSON mode 加本地结构校验，没有测试服务端强制 JSON Schema，因此不能宣称严格 Schema 输出能力已验证。

### Tool Calling：PASS

- 响应 `finish_reason=tool_calls`。
- `message.tool_calls` 存在且为非空数组，调用数为 1。
- 调用类型为 `function`，函数名严格等于 `get_stock_price`。
- `function.arguments` 可被 JSON 解析；参数键严格等于 `date`、`symbol`。
- 脱敏参数摘要：`symbol=600519.SH`，`date=2026-10-10`。
- 参数类型和值符合测试预期。
- 没有依赖普通文本描述进行判定。
- 虚拟工具未执行，金融数据 API 请求数为 0。
- 输入 372、输出 63、合计 435 Token。

## Tool Calling 测试定义

测试只向模型注册以下虚拟工具，没有实现工具函数：

```json
{
  "type": "function",
  "function": {
    "name": "get_stock_price",
    "description": "Get the latest stock price for a symbol on a specified date. Verification-only; the tool will not be executed.",
    "parameters": {
      "type": "object",
      "properties": {
        "symbol": {
          "type": "string",
          "description": "Full security code, for example 600519.SH."
        },
        "date": {
          "type": "string",
          "description": "Query date in YYYY-MM-DD format."
        }
      },
      "required": ["symbol", "date"],
      "additionalProperties": false
    }
  }
}
```

本测试没有向模型提交工具执行结果，因此只验证工具调用请求的生成能力，不验证完整工具循环。

## 尚未验证的能力

- Tool Calling 的完整两阶段循环：执行工具并把 `tool` 结果回传给模型。
- 多工具选择、并行 Tool Calls、无工具场景与工具异常恢复。
- 服务端严格 JSON Schema / strict tool schema；本次 JSON 仅使用 `json_object`，工具参数由本地代码校验。
- 流式输出、长上下文、多轮上下文、并发、限流和超时恢复。
- 生产环境延迟、可用性、峰值/低谷价格和账户账单扣费。本次只记录 Token，不读取余额或账单。
- API 返回业务内容的事实正确性与投资分析质量；本阶段仅验证协议能力。

## 安全与调用边界复核

- Base URL：`https://api.deepseek.com`。
- 唯一模型：`deepseek-flash`；没有自动切换模型或调用其他服务。
- API Key 只从本地 `.env` 读取用于认证；未打印、写入文档或保存到脚本。
- 每个测试一次请求，SDK `max_retries=0`，没有重试。
- 没有安装依赖，没有初始化产品项目，没有访问任何金融 API。
- 临时验证脚本在记录结果后删除。

参考资料：[DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)、[DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)、[Token Usage](https://api-docs.deepseek.com/quick_start/token_usage/)。
