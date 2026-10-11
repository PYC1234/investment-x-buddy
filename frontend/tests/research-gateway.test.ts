import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyBundle, type RunBundle } from '../src/lib/research-gateway';
import { initialThreads } from '../src/data/demo';

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
