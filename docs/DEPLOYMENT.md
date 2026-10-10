# Investment X Buddy 部署准备

本文是 Netlify 前端与 Render 后端的部署操作清单，不代表云端资源已创建或部署成功。执行前确认仓库中没有 `.env`、数据库文件、密钥或受限数据。

## 1. 部署前阻断检查

- 重新运行前端 `typecheck`、`lint`、production build 和后端 Pytest，确认当前提交仍通过。
- 前端审批请求必须继续与后端 `ApprovalRequest` 的 `plan_version`、`allowed_tools` 契约一致。
- 后端 CORS 已在代码中允许研究流程使用的 `GET`、`POST`、`OPTIONS`；上线时仍需把 Netlify 的精确 Origin 写入 `CORS_ORIGINS`。
- 决定后端使用 Fixture Planner 还是 DeepSeek Planner；真实模式必须在后端安全配置 Key。
- SQLite 需要持久磁盘和固定路径，否则重启或重新部署后数据可能丢失。

## 2. GitHub 仓库上传

以下命令只能由用户在确认远程仓库和公开内容后执行。本次文档任务没有运行这些命令。

```powershell
Set-Location C:\Users\29248\Desktop\XBuddy

# 发布前检查；确认输出不含 .env、*.db、node_modules 或密钥
git status --short
git ls-files

# 仅在目录尚不是仓库且用户决定初始化时执行
git init
git add README.md SUBMISSION.md docs frontend backend .gitignore .env.example
git commit -m "Prepare Investment X Buddy submission"
git branch -M main
git remote add origin https://github.com/PYC1234/investment-x-buddy.git
git push -u origin main
```

发布前建议在 GitHub 网页再次搜索 `API_KEY`、`Bearer` 和本地路径。不要提交根目录 `.env`、`frontend/.env.local`、SQLite 文件或云平台凭证。

## 3. 后端：Render

1. 在 Render 创建 Web Service，连接 GitHub 仓库。
2. Root Directory：`backend`。
3. Runtime：Python。
4. Build Command：

   ```text
   pip install -r requirements.txt
   ```

5. Start Command：

   ```text
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

6. 配置环境变量和 Secret。Fixture 演示可设 `PLANNER_MODE=fixture`；DeepSeek 模式设 `PLANNER_MODE=deepseek` 并配置三个 DeepSeek 变量。
7. 若需要跨重启保留数据，挂载 Persistent Disk，例如挂载到 `/var/data`，设置 `SQLITE_PATH=/var/data/investment_x_buddy.db`。
8. 部署后访问 `https://<BACKEND_HOST>/api/v1/health` 和 `/docs`。

SQLite 演示建议单实例、单 Uvicorn worker；多实例会产生文件锁、状态分裂和恢复不一致。正式生产应迁移到托管 PostgreSQL，并将耗时执行放入任务队列。

## 4. 前端：Netlify

仓库根目录已提供 `netlify.toml`，其中配置：

| 设置 | 值 |
|---|---|
| Base directory | `frontend` |
| Build command | `npm run build` |
| Publish directory | `.next` |
| Node.js | `24` |

Netlify 使用 OpenNext 自动适配 Next.js，不需要安装或固定 `@netlify/plugin-nextjs`。按以下步骤发布：

1. 登录 Netlify，选择 **Add new project → Import an existing project**。
2. 选择 GitHub 并授权 Netlify 读取 `PYC1234/investment-x-buddy`。
3. 选择仓库的默认生产分支。Netlify 如自动识别 `frontend`，仍检查最终设置是否与上表一致。
4. Framework 保持 Next.js；不要添加 Functions directory、额外插件或静态导出命令。
5. Render 尚未上线时，不创建 `NEXT_PUBLIC_API_BASE_URL`，直接选择 **Deploy**。部署结果应显示应用自身的 Demo Mode 标识。
6. 部署完成后，可在 **Project configuration → Domain management** 修改免费的 `*.netlify.app` 站点名；记下最终生产 Origin。

Render 上线后切换真实 API：

1. 在 Netlify 打开 **Project configuration → Environment variables → Add a variable**。
2. 添加 `NEXT_PUBLIC_API_BASE_URL=https://<RENDER_SERVICE>.onrender.com`，值只包含 HTTPS Origin，不带 `/api/v1`，Scope 至少包含 Builds，Deploy context 选择 Production。
3. 在 Render 设置 `CORS_ORIGINS` 为包含 Netlify 精确生产 Origin 的 JSON 数组，例如：

   ```json
   ["https://<YOUR_NETLIFY_PROJECT>.netlify.app"]
   ```

4. 重新部署 Render，再在 Netlify 触发一次新的 production deploy。`NEXT_PUBLIC_*` 会进入浏览器构建产物，变量变化后必须重新构建。
5. 打开页面确认显示 FastAPI 模式并执行完整研究流程。连接失败时页面应报错，不能把错误当成 Demo 成功。

不要把 `DEEPSEEK_API_KEY`、`FUYAO_API_KEY`、数据库凭证或任何后端 Secret 配置到 Netlify。`NEXT_PUBLIC_API_BASE_URL` 本身是公开地址。

## 5. 环境变量清单

### Netlify

| 变量 | 必需 | 说明 |
|---|---:|---|
| `NEXT_PUBLIC_API_BASE_URL` | Demo 模式不设置；真实模式必需 | Render 的 FastAPI HTTPS Origin，不含 `/api/v1`；修改后重新部署 |

### Render

| 变量 | 必需 | 示例或说明 |
|---|---:|---|
| `PLANNER_MODE` | 是 | `fixture` 或 `deepseek` |
| `CORS_ORIGINS` | 是 | `["https://your-project.netlify.app"]`，必须是合法 JSON 数组和精确 Origin |
| `SQLITE_PATH` | 推荐 | 持久磁盘内的绝对路径 |
| `DEEPSEEK_API_KEY` | DeepSeek 模式 | Secret；不要输出到日志 |
| `DEEPSEEK_BASE_URL` | DeepSeek 模式 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | DeepSeek 模式 | 已验证记录使用 `deepseek-flash` |
| `MAX_TOOL_CALLS` | 否 | 默认 8 |
| `MAX_EXECUTION_ROUNDS` | 否 | 默认 8 |
| `RUN_TIMEOUT_SECONDS` | 否 | 默认 30 |
| `MAX_TOOL_RETRIES` | 否 | 默认 1 |
| `DEEPSEEK_INPUT_COST_PER_1M` | 否 | 未配置时成本状态为 `NOT_CONFIGURED` |
| `DEEPSEEK_OUTPUT_COST_PER_1M` | 否 | 同上 |

`FUYAO_API_KEY`、`DATABASE_URL` 已在配置类中保留，但当前执行路径未使用，不应因为变量存在就宣称已接通。

## 6. CORS 验收

后端应只允许实际 Netlify 生产 Origin。部署后从浏览器执行创建 Run、批准、恢复和取消，确认预检和 `POST` 均成功。检查响应不能包含 Key 或请求中的敏感值。若站点改名或绑定自定义域名，必须同步更新 Render 的 `CORS_ORIGINS`。

## 7. 线上健康检查

```powershell
$backend = 'https://<BACKEND_HOST>'
$frontend = 'https://<FRONTEND_HOST>'

Invoke-RestMethod "$backend/api/v1/health"
Invoke-WebRequest $frontend -Method Head
Invoke-WebRequest "$backend/docs" -Method Head
```

预期：健康接口返回服务名、版本、状态和时间；前端与 OpenAPI 返回 2xx。健康通过不等于研究主链路通过。

## 8. 线上完整研究流程验收

1. 打开前端，确认显示 FastAPI 模式，而不是 Demo Mode。
2. 新建 Thread，输入不含隐私的测试目标。
3. 提交后确认后端生成 Run，状态为 `PENDING_APPROVAL`，计划工具均来自 Registry。
4. 检查审批卡显示计划版本和工具范围；批准后确认执行状态变化。
5. 查看 Task 和 Tool Call，确认耗时、尝试次数与错误可追踪。
6. 查看 Evidence，确认 `is_demo=true` 和 DEMO DATA 标签；不得把 Fixture 当实时行情。
7. 查看 Report，逐项确认 Finding 引用了存在的 Evidence ID，并显示缺失信息。
8. 刷新页面，确认 Run ID 和状态可恢复；执行 resume 时不重复已完成 Task。
9. 使用 Fixture 失败目标验证重试、`PARTIAL`、停止原因和恢复入口。
10. 验证取消、旧计划版本审批、未注册工具和无效参数返回明确错误。
11. 检查浏览器控制台、移动端布局和后端日志；确认无 Key、认证头和敏感请求值。
12. 重启后端实例，验证持久磁盘中的 SQLite 数据仍存在。

把最终 URL、验收日期、部署版本和结果填写到根目录 `SUBMISSION.md`。任何未执行步骤保留为待验证。
