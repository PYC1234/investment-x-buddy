# Investment X Buddy 提交清单

更新时间：2026-10-10

## 公开链接

- Web 产品：`https://relaxed-cuchufli-47f2fa.netlify.app/`
- GitHub 仓库：`https://github.com/PYC1234/investment-x-buddy.git`
- 后端健康检查：`https://investment-x-buddy.onrender.com/api/v1/health`
- 可选演示视频：`record.mp4`（随交付包附带，9.8 MB）

当前状态：Render 后端与 Netlify 前端均已公开上线并通过健康检查与预检 CORS；前端已切至 FASTAPI MODE 并与后端联通。

## 必交材料

- [x] 根目录 `README.md`
- [x] `docs/AI_DEVELOPMENT_LOG.md`
- [x] `docs/ARCHITECTURE.md`
- [x] `docs/DEPLOYMENT.md`
- [x] Stage 0 环境、数据源和风险审计记录
- [x] Stage 0.5 DeepSeek 最小能力验证记录
- [x] 公开 Web URL（Netlify）
- [x] 公开 GitHub URL
- [x] Stage 3 前后端本地端到端验收结果
- [x] 云端健康检查（Render `/api/v1/health` → 200）
- [x] 云端完整研究流程验收（线上全链路）
- [x] 仓库密钥与受限文件最终扫描

## 已有测试记录

| 范围 | 已记录结果 | 提交前动作 |
|---|---|---|
| DeepSeek 最小验证 | 文本、JSON Output、Tool Calling 均 PASS；3 次请求、685 Token；虚拟工具未执行 | 保留记录，不重复产生费用 |
| 前端 | Stage 3 后 TypeScript、ESLint、production build 通过；Netlify 静态导出（`out/`）已上线 | 线上页面显示 FASTAPI MODE |
| 后端 | Stage 3 后 Pytest 11 项通过；Render free 实例 `/api/v1/health` 200 | 线上主链路已跑通 |
| 端到端 | 本地与线上 Fixture Planner 全流程通过：创建、计划、审批、工具、Evidence、Report、事件与刷新恢复 | 线上 FastAPI 模式已完成同一流程 |

## 已知限制

- 当前金融工具使用 Fixture；所有数值必须显示 DEMO DATA，不能称为实时行情。
- 实时扶摇/iFinD 数据源尚未接入执行链路。
- 没有用户认证、租户隔离或敏感投资组合保护，公开演示不得输入隐私数据。
- SQLite 云端持久化依赖挂载磁盘；多实例与多 worker 不适合当前实现。
- 持久化事件的实时 SSE、分布式队列、跨进程强取消尚未实现。
- Report 为确定性 Evidence 汇总；没有独立 Artifact 存储、导出或版本管理。
- DeepSeek Planner 的云端端到端流程和 Render 持久磁盘重启恢复仍待验证。

## 最终提交人需填写

- 提交人姓名：`<待填写（请填你的姓名）>`
- GitHub 账号/仓库：`PYC1234 / investment-x-buddy`
- Web URL：`https://relaxed-cuchufli-47f2fa.netlify.app/`
- 后端 URL：`https://investment-x-buddy.onrender.com`
- 最终提交 Commit SHA：`c4b0c28`
- Stage 3 验收日期与结果：`2026-10-10 · 前端 typecheck/lint/build 通过；后端 Pytest 11 项通过；本地 Fixture 全链路通过`
- 云端完整流程验收日期与结果：`2026-10-10 · Render /api/v1/health 200；线上创建→计划→审批→工具(3/3)→Evidence(全部 DEMO)→Report→刷新恢复 全链路通过`
- 是否附演示视频：`是（record.mp4，随交付包附带）`

## 发布前签核

- [x] `.env`、`.env.local`、SQLite 文件和密钥未进入 Git（仓库内无真实密钥）
- [x] README 中的状态与最终代码一致
- [x] Demo/Fixture 标识在前端、Evidence 和 Report 中可见（LOCAL DEMO / FASTAPI MODE 徽标）
- [x] CORS 仅允许真实前端 Origin，并支持所需请求方法（预检已验 200）
- [x] Render 未上线时，Netlify 未设置 `NEXT_PUBLIC_API_BASE_URL`，页面显示 Demo Mode（已完成）
- [x] Render 上线后，Netlify 的 `NEXT_PUBLIC_API_BASE_URL` 指向 HTTPS 后端 Origin，并已重新部署（已切 FASTAPI MODE）
- [x] 后端 Secret 只保存在云平台秘密变量中（Render 未设 DeepSeek Key，fixture 模式零付费）
- [x] 公开 URL 在未登录浏览器可操作
- [x] 创建 → 计划 → 审批 → 执行 → Evidence → Report 全流程通过
- [ ] 失败、取消、恢复和刷新恢复完成验收（已记录本地验收）
- [x] 已知限制没有被描述为已完成功能
