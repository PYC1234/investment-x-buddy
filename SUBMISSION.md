# Investment X Buddy 提交清单

更新时间：2026-10-10（Asia/Shanghai）

## 公开链接

- Web 产品：`<待填写：公开 Netlify URL>`
- GitHub 仓库：`https://github.com/PYC1234/investment-x-buddy.git`（待在未登录窗口验证公开访问）
- 后端健康检查：`<待填写：https://.../api/v1/health>`
- 可选演示视频：`<待填写或删除>`

当前尚未创建或验证公开链接。填写后需要在未登录浏览器中复核访问权限。

## 必交材料

- [x] 根目录 `README.md`
- [x] `docs/AI_DEVELOPMENT_LOG.md`
- [x] `docs/ARCHITECTURE.md`
- [x] `docs/DEPLOYMENT.md`
- [x] Stage 0 环境、数据源和风险审计记录
- [x] Stage 0.5 DeepSeek 最小能力验证记录
- [ ] 公开 Web URL
- [ ] 公开 GitHub URL
- [x] Stage 3 前后端本地端到端验收结果
- [ ] 云端健康检查和完整研究流程验收
- [ ] 仓库密钥与受限文件最终扫描

## 已有测试记录

| 范围 | 已记录结果 | 提交前动作 |
|---|---|---|
| DeepSeek 最小验证 | 文本、JSON Output、Tool Calling 均 PASS；3 次请求、685 Token；虚拟工具未执行 | 保留记录，不重复产生费用，除非配置或模型改变 |
| 前端 | Stage 3 后 TypeScript、ESLint、production build 通过；Demo 状态机及 API Adapter 已验收 | Netlify 部署后检查 production build 日志与页面 |
| 后端 | Stage 3 后 Pytest 11 项通过，覆盖主链路、恢复、停止规则、CORS、SSE 和错误脱敏 | Render 部署后执行健康检查和线上主链路 |
| 端到端 | 本地 Fixture Planner 流程已通过：创建、计划、审批、工具、Evidence、Report、事件与刷新恢复 | 云端再次完成同一流程 |

## 已知限制

- 当前金融工具使用 Fixture；所有数值必须显示 DEMO DATA，不能称为实时行情。
- 实时扶摇/iFinD 数据源尚未接入执行链路。
- 没有用户认证、租户隔离或敏感投资组合保护，公开演示不得输入隐私数据。
- SQLite 云端持久化依赖挂载磁盘；多实例与多 worker 不适合当前实现。
- 持久化事件的实时 SSE、分布式队列、跨进程强取消尚未实现。
- Report 为确定性 Evidence 汇总；没有独立 Artifact 存储、导出或版本管理。
- DeepSeek Planner 的云端端到端流程和 Render 持久磁盘重启恢复仍待验证。

## 最终提交人需填写

- 提交人姓名：`<待填写>`
- GitHub 账号/仓库：`<待填写>`
- Web URL：`<待填写>`
- 后端 URL：`<待填写>`
- 最终提交 Commit SHA：`<待填写>`
- Stage 3 验收日期与结果：`<待填写>`
- 云端完整流程验收日期与结果：`<待填写>`
- 是否附演示视频：`<待填写>`

## 发布前签核

- [ ] `.env`、`.env.local`、SQLite 文件和密钥未进入 Git
- [ ] README 中的状态与最终代码一致
- [ ] Demo/Fixture 标识在前端、Evidence 和 Report 中可见
- [ ] CORS 仅允许真实前端 Origin，并支持所需请求方法
- [ ] Render 未上线时，Netlify 未设置 `NEXT_PUBLIC_API_BASE_URL`，页面明确显示 Demo Mode
- [ ] Render 上线后，Netlify 的 `NEXT_PUBLIC_API_BASE_URL` 指向 HTTPS 后端 Origin，并已重新部署
- [ ] 后端 Secret 只保存在云平台秘密变量中
- [ ] 公开 URL 在未登录浏览器可操作
- [ ] 创建 → 计划 → 审批 → 执行 → Evidence → Report 全流程通过
- [ ] 失败、取消、恢复和刷新恢复完成验收
- [ ] 已知限制没有被描述为已完成功能
