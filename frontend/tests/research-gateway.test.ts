import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ResearchPlan } from '../src/components/research-plan';
import { ResearchReport } from '../src/components/research-report';
import { buildExampleGoal } from '../src/components/research-input';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyBundle, type RunBundle } from '../src/lib/research-gateway';
import { initialThreads } from '../src/data/demo';

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
  assert.match(html, /未通过，异常证据已排除/);
});

test('示例目标必须包含当前证券代码或明确的预置公司', () => {
  assert.match(buildExampleGoal({ company: '研究工作台', code: '' }, '估值与风险'), /贵州茅台（600519.SH）/);
  assert.match(buildExampleGoal({ company: '招商银行', code: '600036.SH' }, '盈利能力分析'), /招商银行（600036.SH）/);
  assert.match(buildExampleGoal({ company: '尚未指定证券', code: '002594.SZ' }, '估值与风险'), /请对002594.SZ/);
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
  const html = renderToStaticMarkup(createElement(ResearchPlan, {thread, expanded: null, setExpanded: () => {}, onAction: () => {}, mode: 'api'}));
  assert.match(html, /本次研究确认/);
  assert.match(html, /招商银行/);
  assert.match(html, /600036.SH/);
  assert.match(html, /年度利润表/);
  assert.match(html, /不良贷款率尚未接入/);
  assert.match(html, /批准并执行/);
});


test('失败任务提供独立重试入口、错误原因和原始状态版本', () => {
  const input = bundle();
  input.run.status = 'PARTIAL';
  input.run.approval = {plan_version: 1, allowed_tools: ['get_market_snapshot'], approved_at: '2026-10-11T00:00:00Z'};
  input.run.tasks[0].status = 'FAILED';
  input.run.tasks[0].error = 'Mock provider timeout';
  const thread = applyBundle(initialThreads[0], input);
  assert.equal(thread.remoteUpdatedAt, input.run.updated_at);
  const html = renderToStaticMarkup(createElement(ResearchPlan, {thread, expanded: null, setExpanded: () => {}, onAction: () => {}, mode: 'api'}));
  assert.match(html, /重试失败任务/);
  assert.match(html, /Mock provider timeout/);
  assert.match(html, /调用预算不重置/);
});
