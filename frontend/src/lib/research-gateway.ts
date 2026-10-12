import { datasets, evidence, initialThreads, toolsRegistry } from '@/data/demo';
import type { ApiRunStatus, Dataset, Preferences, ResearchEvidence, ResearchReportData, ResearchTask, ResearchThread, ToolCall, ToolDefinition, TraceEvent } from '@/types/research';

export type AppMode = 'api' | 'demo';
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };
export interface ApiTask { id: string; position: number; title: string; tool_name: string; arguments: Record<string, unknown>; rationale: string; status: string; attempts: number; evidence_id: string | null; error: string | null }
export interface ApiPlan { research_type?: string; scope?: string[]; limitations?: string[]; research_goal: string; tasks: Array<{ title: string; tool_name: string; arguments: Record<string, unknown>; rationale: string }> }
export interface ApiReport { title: string; status: string; data_notice: string; quality_status?: string; executive_summary: string; findings: Array<{ task: string; statement: string; evidence_ids: string[] }>; missing_information: string[]; evidence_ids: string[] }
export interface ApiRun { id: string; thread_id: string; goal: string; status: ApiRunStatus; plan_version: number; planner_mode: string; plan: ApiPlan | null; approval: { plan_version: number; allowed_tools: string[]; approved_at: string } | null; report: ApiReport | null; error: string | null; created_at: string; updated_at: string; started_at: string | null; completed_at: string | null; tasks: ApiTask[]; usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number; estimated_cost_usd: number | null; cost_status: string } }
export interface ApiEvent { id: number; event_type: string; data: Record<string, unknown>; created_at: string }
export interface ApiEvidence { id: string; task_id: string; tool_name: string; title: string; data: Record<string, unknown>; is_demo: boolean; created_at: string }
export interface ApiToolCall { id: string; tool_name: string; attempt: number; status: string; duration_ms: number; error: string | null; created_at: string }
export interface ApiCheckpoint { sequence: number; before_chars: number; after_chars: number; context_summary: string; created_at: string }
export interface ApiTool { name: string; description: string; parameters: Record<string, unknown>; data_source: string }
export interface ApiThread { id: string; title: string; created_at: string; updated_at: string; memory: Record<string, unknown>; runs: Array<{ id: string; goal: string; status: ApiRunStatus; planner_mode: string; created_at: string; updated_at: string }> }
export interface RunBundle { run: ApiRun; events: ApiEvent[]; evidence: ApiEvidence[]; toolCalls: ApiToolCall[]; checkpoints: ApiCheckpoint[]; memory: Record<string, unknown>; tools: ApiTool[]; report: ApiReport | null }

const rawBase = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '');
export const configuredMode: AppMode = rawBase ? 'api' : 'demo';

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  if (!rawBase) return { ok: false, error: '未配置 NEXT_PUBLIC_API_BASE_URL' };
  try {
    const response = await fetch(`${rawBase}${path}`, { cache: 'no-store', ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
    if (!response.ok) {
      let detail = '';
      try { const body = await response.json() as { error?: { message?: string } }; detail = body.error?.message ? ` · ${body.error.message}` : ''; } catch { /* non-JSON error */ }
      return { ok: false, error: `API ${response.status}: ${response.statusText}${detail}` };
    }
    return { ok: true, data: await response.json() as T };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return { ok: false, error: 'REQUEST_ABORTED' };
    return { ok: false, error: error instanceof Error ? error.message : '无法连接 FastAPI' };
  }
}

async function loadRunBundle(id: string, signal?: AbortSignal): Promise<ApiResult<RunBundle>> {
  const runResult = await request<ApiRun>(`/api/v1/runs/${id}`, { signal });
  if (!runResult.ok) return runResult;
  const [events, evidenceResult, toolCalls, checkpoints, memory, tools] = await Promise.all([
    request<ApiEvent[]>(`/api/v1/runs/${id}/events`, { signal }),
    request<ApiEvidence[]>(`/api/v1/runs/${id}/evidence`, { signal }),
    request<ApiToolCall[]>(`/api/v1/runs/${id}/tool-calls`, { signal }),
    request<ApiCheckpoint[]>(`/api/v1/runs/${id}/checkpoints`, { signal }),
    request<Record<string, unknown>>(`/api/v1/runs/${id}/memory`, { signal }),
    request<ApiTool[]>('/api/v1/tools', { signal }),
  ]);
  if (!events.ok) return events;
  if (!evidenceResult.ok) return evidenceResult;
  if (!toolCalls.ok) return toolCalls;
  if (!checkpoints.ok) return checkpoints;
  if (!memory.ok) return memory;
  if (!tools.ok) return tools;
  let report: ApiReport | null = runResult.data.report;
  if (report) {
    const reportResult = await request<ApiReport>(`/api/v1/runs/${id}/report`, { signal });
    if (!reportResult.ok) return reportResult;
    report = reportResult.data;
  }
  return { ok: true, data: { run: runResult.data, events: events.data, evidence: evidenceResult.data, toolCalls: toolCalls.data, checkpoints: checkpoints.data, memory: memory.data, tools: tools.data, report } };
}

function uiStatus(status: ApiRunStatus): ResearchThread['status'] {
  return ({ PLANNING: 'running', PENDING_APPROVAL: 'approval', APPROVED: 'running', RUNNING: 'running', COMPLETE: 'completed', PARTIAL: 'partial', FAILED: 'failed', REJECTED: 'rejected', CANCELLED: 'cancelled' } as const)[status];
}
function eventKind(type: string): TraceEvent['kind'] {
  if (type.includes('failed') || type.includes('invalid')) return 'error';
  if (type.includes('rejected') || type.includes('cancelled')) return 'warning';
  if (type.includes('completed') || type.includes('approved') || type.includes('saved')) return 'success';
  return 'info';
}
function formatMetric(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : '—';
}
function evidencePeriod(item: ApiEvidence): string {
  if (item.data.fiscal_year != null) return `${item.data.fiscal_year} 年度`;
  const timestamp = item.data.timestamp_ms;
  if (typeof timestamp === 'number' && Number.isFinite(timestamp)) return new Date(timestamp).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) + '（北京时间）';
  return String(item.data.as_of ?? (item.is_demo ? 'Fixture snapshot' : '时间未提供'));
}
function mapEvidence(item: ApiEvidence): ResearchEvidence {
  const quality = item.data.quality as { status?: string; issues?: { message: string }[] } | undefined;
  const limitation = [item.data.missing_information, ...(quality?.issues?.map(issue => issue.message) ?? [])].filter(Boolean).join('；');
  return { id: item.id, title: item.title, type: item.tool_name, period: evidencePeriod(item), detail: JSON.stringify(item.data, null, 2), limitation: limitation || (item.is_demo ? 'FIXTURE / DEMO DATA；并非实时金融数据。' : '质量未检查；扶摇接口时间不保证为成交时间，尚未交叉核验。'), isDemo: item.is_demo, toolName: item.tool_name, data: item.data };
}
function mapReport(report: ApiReport | null): ResearchReportData | null {
  return report ? { title: report.title, status: report.status, qualityStatus: report.quality_status ?? 'NOT_CHECKED', dataNotice: report.data_notice, executiveSummary: report.executive_summary, findings: report.findings.map(item => ({ task: item.task, statement: item.statement, evidenceIds: item.evidence_ids })), missingInformation: report.missing_information, evidenceIds: report.evidence_ids } : null;
}
function evidenceDataset(items: ApiEvidence[], report: ApiReport | null): Dataset | null {
  if (!items.length) return null;
  items = items.filter(item => (item.data.quality as { usable?: boolean } | undefined)?.usable !== false);
  if (!items.length) return { isDemo: false, metrics: [{ label: '市盈率 PE (TTM)', value: '—', unit: '倍', note: '证据质量未通过' }, { label: '市净率 PB', value: '—', unit: '倍', note: '证据质量未通过' }, { label: '净资产收益率 ROE', value: '—', unit: '%', note: '证据质量未通过' }], prices: [], financials: [], findings: [] };
  const snapshot = items.find(item => item.tool_name === 'get_market_snapshot')?.data;
  const valuation = items.find(item => item.tool_name === 'get_valuation_snapshot')?.data.valuation as Record<string, unknown> | null | undefined;
  const financial = items.find(item => item.tool_name === 'get_financial_summary')?.data.financials as Record<string, unknown> | null | undefined;
  const isDemo = items.some(item => Boolean(item.is_demo));
  const financialData = items.find(item => item.tool_name === 'get_financial_summary')?.data;
  const prices = Array.isArray(snapshot?.prices) ? snapshot.prices as {date: string; price: number}[] : [];
  const history = Array.isArray(financialData?.financial_history) ? financialData.financial_history as {year: string; revenue: number; profit: number}[] : [];
  return {
    isDemo,
    metrics: [
      { label: '市盈率 PE (TTM)', value: formatMetric(valuation?.pe_ttm), unit: '倍', note: isDemo ? 'DEMO DATA' : '扶摇 · PE(TTM)' },
      { label: '市净率 PB', value: formatMetric(valuation?.pb), unit: '倍', note: isDemo ? 'DEMO DATA' : '扶摇 · PB(MRQ)' },
      { label: '净资产收益率 ROE', value: formatMetric(financial?.roe_percent), unit: '%', note: isDemo ? 'DEMO DATA' : '利润表未提供 ROE' },
    ],
    prices: prices.filter(row => typeof row.date === 'string' && Number.isFinite(row.price)),
    financials: history.filter(row => Number.isFinite(row.revenue) && Number.isFinite(row.profit)),
    findings: report?.findings.map(item => item.statement) ?? [],
  };
}

export function applyBundle(thread: ResearchThread, bundle: RunBundle): ResearchThread {
  const { run } = bundle;
  const tasks: ResearchTask[] = run.tasks.map(task => ({ id: task.id, position: task.position, title: task.title, toolName: task.tool_name, arguments: task.arguments, rationale: task.rationale, status: task.status, attempts: task.attempts, evidenceId: task.evidence_id, error: task.error }));
  const mappedEvidence = bundle.evidence.map(mapEvidence);
  const calls: ToolCall[] = bundle.toolCalls.map(call => ({ id: call.id, toolName: call.tool_name, attempt: call.attempt, status: call.status, durationMs: call.duration_ms, error: call.error }));
  const latest = bundle.checkpoints.at(-1);
  const code = String(tasks.find(task => typeof task.arguments.symbol === 'string')?.arguments.symbol ?? thread.code);
  const companyNames: Record<string, string> = { '600519.SH': '贵州茅台', '300750.SZ': '宁德时代', '000001.SZ': '平安银行', '000858.SZ': '五粮液', '600036.SH': '招商银行', '601318.SH': '中国平安' };
  const totalLatency = calls.reduce((sum, call) => sum + call.durationMs, 0) / 1000;
  return {
    ...thread, remoteRunId: run.id, remoteThreadId: run.thread_id, remoteUpdatedAt: run.updated_at, goal: run.goal, title: run.goal.slice(0, 60),
    company: companyNames[code] ?? (code || '尚未指定证券'), code, sector: code === '600519.SH' || code === '000858.SZ' ? '食品饮料' : code === '300750.SZ' ? '电池' : ['000001.SZ', '600036.SH', '601318.SH'].includes(code) ? '金融' : '',
    status: uiStatus(run.status), apiStatus: run.status, approval: run.status === 'REJECTED' ? 'rejected' : run.approval ? 'approved' : 'pending',
    step: tasks.filter(task => task.status === 'COMPLETED').length, planVersion: run.plan_version, plannerMode: run.planner_mode,
    researchScope: run.plan ? { type: run.plan.research_type ?? 'comprehensive', scope: run.plan.scope ?? [], limitations: run.plan.limitations ?? [] } : undefined,
    tasks, apiEvidence: mappedEvidence, apiReport: mapReport(bundle.report), toolCalls: calls,
    apiTools: bundle.tools.map((tool): ToolDefinition => ({ name: tool.name, description: tool.description, permission: tool.data_source, parameters: tool.parameters })),
    memory: bundle.memory, calls: calls.length, tokens: run.usage.total_tokens, latency: totalLatency,
    costUsd: run.usage.estimated_cost_usd, costStatus: run.usage.cost_status,
    events: bundle.events.map(event => ({ id: event.id, time: new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false }), title: event.event_type, detail: JSON.stringify(event.data), kind: eventKind(event.event_type), tokens: 0, latency: Number(event.data.duration_ms ?? 0) / 1000 })),
    checkpoint: latest ? { step: tasks.filter(task => task.status === 'COMPLETED').length, calls: calls.length, tokens: run.usage.total_tokens, latency: totalLatency, approval: run.approval ? 'approved' : 'pending', sequence: latest.sequence, beforeChars: latest.before_chars, afterChars: latest.after_chars } : null,
    recovered: bundle.events.some(event => event.event_type === 'run.resumed'), updated: new Date(run.updated_at).toLocaleTimeString('zh-CN', { hour12: false }),
    apiDataset: evidenceDataset(bundle.evidence, bundle.report), loading: false,
  };
}

export const researchApi = {
  tools: (signal?: AbortSignal) => request<ApiTool[]>('/api/v1/tools', { signal }),
  createRun: (goal: string, preferences: Preferences, signal?: AbortSignal) => request<ApiRun>('/api/v1/runs', { method: 'POST', body: JSON.stringify({ goal, preferences }), signal }),
  getRunBundle: loadRunBundle,
  approve: (id: string, planVersion: number, allowedTools: string[], signal?: AbortSignal) => request<ApiRun>(`/api/v1/runs/${id}/approve`, { method: 'POST', body: JSON.stringify({ plan_version: planVersion, allowed_tools: allowedTools }), signal }),
  reject: (id: string, planVersion: number, reason: string, signal?: AbortSignal) => request<ApiRun>(`/api/v1/runs/${id}/reject`, { method: 'POST', body: JSON.stringify({ plan_version: planVersion, reason }), signal }),
  resume: (id: string, signal?: AbortSignal) => request<ApiRun>(`/api/v1/runs/${id}/resume`, { method: 'POST', signal }),
  retryFailed: (id: string, planVersion: number, updatedAt: string, signal?: AbortSignal) => request<ApiRun>(`/api/v1/runs/${id}/retry-failed`, { method: 'POST', body: JSON.stringify({ plan_version: planVersion, expected_updated_at: updatedAt }), signal }),
  cancel: (id: string, signal?: AbortSignal) => request<ApiRun>(`/api/v1/runs/${id}/cancel`, { method: 'POST', signal }),
  threads: (signal?: AbortSignal) => request<ApiThread[]>('/api/v1/threads', { signal }),
};

export const demoGateway = { getDataset: (code: string): Dataset | null => datasets[code] ?? null, threads: initialThreads, tools: toolsRegistry, evidence };
