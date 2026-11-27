import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ResearchPlan } from '../src/components/research-plan';
import { ResearchReport } from '../src/components/research-report';
import { buildExampleGoal } from '../src/components/research-input';
import { ResearchInput } from '../src/components/research-input';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyBundle, type RunBundle } from '../src/lib/research-gateway';
import { initialThreads } from '../src/data/demo';

test('资料问题复用研究输入框，附件模式不显示股票示例或新页面链接',()=>{
  const html=renderToStaticMarkup(createElement(ResearchInput,{thread:initialThreads[0],goal:'比较附件费用',setGoal:()=>{},onStart:()=>{},documentMode:true},createElement('span',null,'添加对话资料')));
  assert.match(html,/资料问答/);
  assert.match(html,/发送资料问题/);
  assert.match(html,/添加对话资料/);
  assert.doesNotMatch(html,/贵州茅台|href="\/documents"/);
});

test('质量失败证据保留供复核但不进入图表或指标，报告显示质量状态', () => {
  const data = bundle();
  for (const item of data.evidence) item.data.quality = { status: 'FAIL', usable: false, issues: [{ message: '来源时间异常' }] };
  data.report = { title: '质量检查报告', status: 'PARTIAL', quality_status: 'FAIL', data_notice: '接口数据，质量提示为准', executive_summary: '异常证据已排除', findings: [], missing_information: ['来源时间异常'], evidence_ids: ['ev1'] };
  const mapped = applyBundle(initialThreads[0], data);
  assert.equal(mapped.apiEvidence?.length, 3);
  assert.equal(mapped.apiDataset?.prices.length, 0);
  assert.equal(mapped.apiDataset?.financials.length, 0);
  assert.equal(mapped.apiDataset?.metrics[0].value, '—');
  assert.match(mapped.apiEvidence![0].limitation, /来源时间异常/);
  const html = renderToStaticMarkup(createElement(ResearchReport, { thread: mapped, data: mapped.apiDataset ?? null, mode: 'api', onEvidence: () => {} }));
  assert.match(html, /有证据未通过检查/);
  assert.match(html, /异常证据已排除/);
});

test('示例目标必须包含当前证券代码或明确的预置公司', () => {
  assert.match(buildExampleGoal({ company: '研究工作台', code: '' }, '估值与风险'), /贵州茅台（600519.SH）/);
  assert.match(buildExampleGoal({ company: '招商银行', code: '600036.SH' }, '盈利能力分析'), /招商银行（600036.SH）/);
  assert.match(buildExampleGoal({ company: '尚未指定证券', code: '002594.SZ' }, '估值与风险'), /请对002594.SZ/);
});

test('相同证据限制合并展示，并保留各自的证据入口', () => {
  const input = bundle();
  input.evidence[0].id = 'EVD-AAAA';
  input.evidence[1].id = 'EVD-BBBB';
  input.report = {
    title: '研究报告', status: 'COMPLETE', data_notice: '', executive_summary: '', findings: [], evidence_ids: [],
    missing_information: [
      '[EVD-AAAA] 仅作接口级质量检查，未与交易所公告或独立来源交叉核验。',
      '[EVD-BBBB] 仅作接口级质量检查，未与交易所公告或独立来源交叉核验。',
      '扶摇接口数据尚未与交易所原始公告交叉核验。',
    ],
  };
  const thread = applyBundle(initialThreads[0], input);
  const html = renderToStaticMarkup(createElement(ResearchReport, { thread, data: null, mode: 'api', onEvidence: () => {} }));
  assert.equal(html.match(/尚待独立来源交叉核验/g)?.length, 1);
  assert.match(html, /查看证据 EVD-AAAA/);
  assert.match(html, /查看证据 EVD-BBBB/);
});

test('行情与估值问题在摘要优先显示相关证据', () => {
  const input = bundle();
  input.run.goal = '招商银行股价走势怎样？结合市盈率和市净率看估值风险。';
  input.report = {
    title: '研究报告', status: 'COMPLETE', data_notice: '', executive_summary: '', missing_information: [],
    evidence_ids: ['ev1', 'ev2', 'ev3'], findings: [
      { task: '盈利', statement: '年度盈利结果', evidence_ids: ['ev2'] },
      { task: '估值', statement: '估值快照结果', evidence_ids: ['ev3'] },
      { task: '行情', statement: '近期行情结果', evidence_ids: ['ev1'] },
    ],
  };
  const thread = applyBundle(initialThreads[0], input);
  const html = renderToStaticMarkup(createElement(ResearchReport, { thread, data: null, mode: 'api', onEvidence: () => {} }));
  const summary = html.split('详细发现')[0];
  assert.match(summary, /近期行情结果.*估值快照结果/);
  assert.doesNotMatch(summary, /年度盈利结果|财务数据截至/);
});

test('报告首屏只对照可匹配财年的利润与经营现金流', () => {
  const input = bundle();
  input.evidence[1].data.symbol = '600036.SH';
  input.evidence.push({
    id: 'EVD-CASH', task_id: 'cash', tool_name: 'get_fuyao_cash_flow', title: '现金流量表',
    is_demo: false, created_at: input.run.created_at, data: {
      symbol: '600036.SH', records: [
        { period: '2025-12-31', operating_cash_flow: 180_000_000_000 },
        { period: '2026-09-30', operating_cash_flow: 250_000_000_000 },
      ],
    },
  });
  input.report = {
    title: '研究报告', status: 'COMPLETE', data_notice: '', executive_summary: '', missing_information: [],
    evidence_ids: ['ev2', 'EVD-CASH'], findings: [{
      task: '经营现金流与归母净利润对照', statement: '经营现金流净额高于归母净利润。',
      evidence_ids: ['ev2', 'EVD-CASH'],
    }],
  };
  const thread = applyBundle(initialThreads[0], input);
  const html = renderToStaticMarkup(createElement(ResearchReport, { thread, data: null, mode: 'api', onEvidence: () => {} }));
  assert.match(html, /结论摘要/);
  assert.match(html, /2025 财年/);
  assert.match(html, /1,800/);
  assert.doesNotMatch(html, /2026 财年|2,500/);
});

test('定期报告按实际期间显示，并将计算与原文页码一起呈现', () => {
  const input = bundle();
  const source = 'https://static.cninfo.com.cn/finalpage/2026-10-31/1225649896.PDF';
  const evidenceId = 'EVD-PERIODIC';
  input.evidence = [{ id: evidenceId, task_id: 'task', tool_name: 'read_official_periodic_report',
    title: '读取官方定期报告', is_demo: false, created_at: input.run.created_at, data: {
      dataset: 'periodic_filing', period: '2026 年三季报', fiscal_year: 2026, source,
      reasons: [{ page: 3 }],
    } }];
  input.report = {
    title: '定期报告', status: 'COMPLETE', data_notice: '', executive_summary: '', period: '2026 年三季报',
    missing_information: [], evidence_ids: [evidenceId], findings: [
      { task: '现金流对照', kind: 'computed', statement: '同比 +120.07%。', evidence_ids: [evidenceId] },
      { task: '经营活动产生的现金流量净额变动原因', kind: 'disclosed', statement: '公司披露的原因。', evidence_ids: [evidenceId],
        excerpt_refs: [{ evidence_id: evidenceId, collection: 'reasons', record_index: 0 }] },
    ],
    comparisons: [{ label: '经营现金流量净额', period: '2026 年 1–9 月', comparison_period: '2025 年 1–9 月',
      current: 84058979832, previous: 38196802155, change: 120.07, change_basis: '同比', change_kind: 'computed',
      basis: '合并现金流量表', page: 11, evidence_id: evidenceId, source }],
  };
  const thread = applyBundle(initialThreads[0], input);
  assert.equal(thread.apiEvidence?.[0].period, '2026 年三季报');
  assert.equal(thread.apiDataset, null);
  const html = renderToStaticMarkup(createElement(ResearchReport, { thread, data: null, mode: 'api', onEvidence: () => {} }));
  assert.match(html, /2026 年 1–9 月/);
  assert.match(html, /系统计算/);
  assert.match(html, /PDF#page=3/);
  assert.match(html, /PDF#page=11/);
});

function bundle(isDemo = false): RunBundle {
  return {
    run: { id: 'run', thread_id: 'thread', goal: '分析招商银行的风险', status: 'COMPLETE', plan_version: 1, planner_mode: 'fixture', plan: null, approval: null, report: null, error: null, created_at: '2026-10-11T00:00:00Z', updated_at: '2026-10-11T00:00:00Z', started_at: null, completed_at: null, tasks: [{id: 'task', position: 1, title: '行情', tool_name: 'get_market_snapshot', arguments: {symbol: '600036.SH'}, rationale: '研究', status: 'COMPLETED', attempts: 1, evidence_id: 'ev1', error: null}], usage: {prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, estimated_cost_usd: null, cost_status: 'NOT_CONFIGURED'} },
    evidence: [
      {id: 'ev1', task_id: 'task', tool_name: 'get_market_snapshot', title: '行情', is_demo: isDemo, created_at: '2026-10-11T00:00:00Z', data: {symbol: '600036.SH', timestamp_ms: 1791705923000, prices: [{date: '2026-10-09', price: 41.42}]}},
      {id: 'ev2', task_id: 'task', tool_name: 'get_financial_summary', title: '财务', is_demo: isDemo, created_at: '2026-10-11T00:00:00Z', data: {financials: {roe_percent: null}, financial_history: [{year: '2025', revenue: 3375.32, profit: 1501.81}]}},
      {id: 'ev3', task_id: 'task', tool_name: 'get_valuation_snapshot', title: '估值', is_demo: isDemo, created_at: '2026-10-11T00:00:00Z', data: {valuation: {pe_ttm: 6.88618, pb: 0.912285}}},
    ], events: [], toolCalls: [], checkpoints: [], memory: {}, tools: [], report: null,
  };
}

test('真实证据恢复公司、图表、来源、两位小数和可读时间', () => {
  const result = applyBundle(initialThreads[0], bundle());
  assert.equal(result.company, '招商银行');
  assert.equal(result.code, '600036.SH');
  assert.equal(result.apiDataset?.isDemo, false);
  assert.equal(result.apiDataset?.prices.length, 1);
  assert.equal(result.apiDataset?.financials.length, 1);
  assert.equal(result.apiDataset?.metrics[0].value, '6.89');
  assert.equal(result.apiDataset?.metrics[1].value, '0.91');
  assert.equal(result.apiDataset?.metrics[2].value, '—');
  assert.match(result.apiDataset!.metrics[0].note, /扶摇/);
  assert.match(result.apiEvidence![0].period, /北京时间/);
  assert.equal(result.apiEvidence![0].isDemo, false);
});

test('缺失序列保持空白，不填充 Demo 曲线；Demo 仍有明确标识', () => {
  const input = bundle();
  input.evidence[0].data.prices = [];
  input.evidence[1].data.financial_history = [];
  const result = applyBundle(initialThreads[0], input);
  assert.deepEqual(result.apiDataset?.prices, []);
  assert.deepEqual(result.apiDataset?.financials, []);
  const demo = applyBundle(initialThreads[0], bundle(true));
  assert.equal(demo.apiDataset?.isDemo, true);
  assert.equal(demo.apiDataset?.metrics[0].note, 'DEMO DATA');
});


test('确认卡范围来自后端计划，而非前端猜测', () => {
  const input = bundle();
  input.run.plan = {research_goal: input.run.goal, research_type: 'risk', scope: ['最近行情', '年度利润表'], limitations: ['不良贷款率尚未接入'], tasks: []};
  const result = applyBundle(initialThreads[0], input);
  assert.equal(result.researchScope?.type, 'risk');
  assert.deepEqual(result.researchScope?.scope, ['最近行情', '年度利润表']);
  assert.deepEqual(result.researchScope?.limitations, ['不良贷款率尚未接入']);
});


test('审批页面渲染标的、范围、缺口与批准按钮', () => {
  const input = bundle();
  input.run.status = 'PENDING_APPROVAL';
  input.run.plan = {research_goal: input.run.goal, research_type: 'risk', scope: ['年度利润表'], limitations: ['不良贷款率尚未接入'], tasks: []};
  const thread = applyBundle(initialThreads[0], input);
  const html = renderToStaticMarkup(createElement(ResearchPlan, {thread, expanded: null, setExpanded: () => {}, onAction: () => {}, onRevise: async () => null, mode: 'api'}));
  assert.match(html, /本次研究确认/);
  assert.match(html, /招商银行/);
  assert.match(html, /600036.SH/);
  assert.match(html, /年度利润表/);
  assert.match(html, /不良贷款率尚未接入/);
  assert.match(html, /批准并执行/);
  assert.match(html, /<textarea id="research-plan-feedback"/);
  assert.match(html, /生成新版计划/);
  assert.doesNotMatch(html, /推进下一演示步骤|模拟工具失败/);
});


test('失败任务提供独立重试入口、错误原因和原始状态版本', () => {
  const input = bundle();
  input.run.status = 'PARTIAL';
  input.run.approval = {plan_version: 1, allowed_tools: ['get_market_snapshot'], approved_at: '2026-10-11T00:00:00Z'};
  input.run.tasks[0].status = 'FAILED';
  input.run.tasks[0].error = 'Mock provider timeout';
  const thread = applyBundle(initialThreads[0], input);
  assert.equal(thread.remoteUpdatedAt, input.run.updated_at);
  const html = renderToStaticMarkup(createElement(ResearchPlan, {thread, expanded: null, setExpanded: () => {}, onAction: () => {}, onRevise: async () => null, mode: 'api'}));
  assert.match(html, /重试失败任务/);
  assert.match(html, /Mock provider timeout/);
  assert.match(html, /调用预算不重置/);
});
