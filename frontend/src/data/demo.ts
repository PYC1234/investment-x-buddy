import type { Dataset, ResearchThread, RunStatus } from '@/types/research';

export const statusLabels: Record<RunStatus, string> = { idle: '待开始', running: '研究中', approval: '等待审批', paused: '已暂停', completed: '已完成', partial: '部分完成', cancelled: '已取消', failed: '执行失败', rejected: '已拒绝' };
export const steps = [
  { title: '解析目标与规划研究', tool: 'research_planner', detail: '识别研究范围、时间窗口与证据要求，生成可调整的五步计划。' },
  { title: '整理行情与财务样本', tool: 'market_snapshot', detail: '读取本地演示数据集，整理估值、盈利能力与年度财务趋势。' },
  { title: '扩展行业对比', tool: 'peer_comparison', detail: '敏感能力需审批：演示额外数据访问与预算授权。拒绝后跳过此步骤。' },
  { title: '交叉验证与风险分析', tool: 'evidence_checker', detail: '检查证据覆盖、时间范围和指标口径。压缩上下文并保留引用。' },
  { title: '生成研究报告', tool: 'report_builder', detail: '将演示样本组织为结论、风险与证据引用。不会生成真实投资建议。' },
];
export const toolsRegistry = [
  { name: 'market_snapshot', description: '行情与估值快照', permission: '只读 · 已允许' },
  { name: 'financial_statements', description: '财务数据整理', permission: '只读 · 已允许' },
  { name: 'peer_comparison', description: '行业可比样本', permission: '扩展访问 · 需审批' },
  { name: 'evidence_checker', description: '证据核对与引用', permission: '只读 · 已允许' },
  { name: 'report_builder', description: '研究报告生成', permission: '本地产物 · 已允许' },
];
export const evidence = [
  { id: 'E01', title: '年度财务样本', type: 'Financial statements', period: '2021–2025 · 年度', detail: '人工构造的收入、利润和盈利能力序列，用于展示财务趋势与引用交互。不是公司公告，也未从交易所获取。', limitation: '未经审计，不具备实际财务解释力。' },
  { id: 'E02', title: '行情与估值样本', type: 'Market snapshot', period: '2025.10–2026.09 · 月度', detail: '本地生成的价格、PE 与 PB 展示样本。未连接行情服务，价格不代表证券的真实历史走势。', limitation: '不适用于交易、估值判断或收益计算。' },
  { id: 'E03', title: '研究方法与风险清单', type: 'Research methodology', period: '模板版本 1.0', detail: '展示证据链结构：研究问题 → 指标 → 样本来源 → 局限性。结论仅用于测试报告排版与流程。', limitation: '缺少真实公告、行业数据和独立来源交叉验证。' },
];
const priceShape = [132, 138, 134, 143, 139, 147, 150, 145, 158, 153, 162, 168];
export const datasets: Record<string, Dataset> = Object.fromEntries([
  ['600519.SH', 10, ['28.6', '8.4', '29.3'], ['演示样本中的收入与利润同步增长，适合进一步拆解增长来源。', '盈利能力指标在样本期内保持稳定，仍需检验现金流匹配程度。', '估值需要结合行业与周期解释，单一倍数不足以形成结论。']],
  ['300750.SZ', 2, ['24.8', '4.2', '17.8'], ['样本收入呈增长趋势，但利润弹性需要结合产能利用率验证。', '演示盈利能力有所改善，尚未覆盖原材料价格变化。', '资本开支与竞争强度应作为后续证据补充方向。']],
  ['002594.SZ', 1.5, ['21.2', '3.8', '19.1'], ['本地样本展示销量扩张下的收入增长路径。', '利润增速与收入增速存在差异，应进一步拆解产品结构。', '海外业务及价格竞争属于待补充证据的风险项。']],
].map(([code, factor, values, findings]) => [code, {
  metrics: (values as string[]).map((value, i) => ({ label: ['市盈率 PE (TTM)', '市净率 PB', '净资产收益率 ROE'][i], value, unit: i === 2 ? '%' : '倍', note: ['盈利估值', '资产估值', '盈利能力'][i] })),
  prices: priceShape.map((v, i) => ({ date: `${i < 3 ? '2025' : '2026'}-${String((i + 9) % 12 + 1).padStart(2, '0')}`, price: +(v * (factor as number)).toFixed(2) })),
  financials: [2021, 2022, 2023, 2024, 2025].map((y, i) => ({ year: String(y), revenue: Math.round((840 + i * 158) * (factor as number) / 10), profit: Math.round((360 + i * 85) * (factor as number) / 10) })), findings,
}])) as Record<string, Dataset>;
export function createThread(id: string, company = '自定义研究', code = '', title = '新的研究线程', status: RunStatus = 'idle'): ResearchThread {
  const step = status === 'completed' ? 5 : status === 'approval' ? 2 : 0;
  return { id, title, company, code, sector: code === '600519.SH' ? '食品饮料' : code === '300750.SZ' ? '电力设备' : code ? '汽车' : '待选研究标的', goal: code ? `分析${company}的盈利能力、估值水平与主要风险，并列出需要进一步验证的证据。` : '', status, step, approval: status === 'completed' ? 'approved' : 'pending', tab: 'Research', events: step ? [{ id: 1, time: '14:32:08', title: '演示研究计划已载入', detail: '恢复预置 UI 场景；未执行真实 Agent 或金融 API。', kind: 'info', tokens: 0, latency: 0 }] : [], calls: step ? 4 : 0, tokens: step ? 4280 : 0, latency: step ? 12.4 : 0, updated: '演示快照 · 14:32', checkpoint: step ? { step: 2, calls: 4, tokens: 4280, latency: 12.4, approval: 'pending' } : null, recovered: false };
}
export const initialThreads = [createThread('maotai', '贵州茅台', '600519.SH', '贵州茅台基本面研究', 'approval'), createThread('catl', '宁德时代', '300750.SZ', '宁德时代盈利能力分析', 'completed'), createThread('byd', '比亚迪', '002594.SZ', '比亚迪估值研究', 'idle')];
