'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, ListChecks, ScrollText, Server } from 'lucide-react';
import { Sidebar } from '@/components/sidebar';
import { ResearchHeader } from '@/components/research-header';
import { ResearchInput } from '@/components/research-input';
import { FinancialCharts, FinancialMetrics } from '@/components/financial-charts';
import { ResearchReport } from '@/components/research-report';
import { ResearchPlan } from '@/components/research-plan';
import { ExecutionTrace } from '@/components/execution-trace';
import { AgentMonitor } from '@/components/agent-monitor';
import { DetailDialog } from '@/components/ui/dialog';
import { createThread, evidence, initialThreads } from '@/data/demo';
import { transition } from '@/lib/demo-machine';
import { applyBundle, configuredMode, demoGateway, researchApi, type AppMode } from '@/lib/research-gateway';
import type { Preferences, ResearchThread, RunAction, WorkspaceTab } from '@/types/research';

const now = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const pollable = new Set(['PLANNING', 'APPROVED', 'RUNNING']);

export function ResearchDashboard() {
  const [threads, setThreads] = useState<ResearchThread[]>(() => configuredMode === 'api' ? [{ ...createThread('api-draft', '研究工作台', '', '新的研究线程'), updated: '尚未创建研究', apiTools: [] }] : initialThreads);
  const [activeId, setActiveId] = useState(configuredMode === 'api' ? 'api-draft' : 'maotai');
  const active = threads.find(thread => thread.id === activeId) ?? threads[0];
  const [goal, setGoal] = useState(active.goal);
  const [mode, setMode] = useState<AppMode>(configuredMode);
  const [apiError, setApiError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(0);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [preferences, setPreferences] = useState<Preferences>({ horizon: '3–5 年', risk: '中等', evidence: true });
  const pollInFlight = useRef(false);
  const restored = useRef(false);

  useEffect(() => {
    if (mode !== 'api') return;
    const controller = new AbortController();
    void researchApi.tools(controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (!result.ok) { setApiError(result.error); return; }
      setThreads(list => list.map(thread => ({ ...thread, apiTools: result.data.map(tool => ({ name: tool.name, description: tool.description, permission: tool.data_source, parameters: tool.parameters })) })));
    });
    return () => controller.abort();
  }, [mode]);

  const data = useMemo(() => mode === 'api' ? active.apiDataset ?? null : demoGateway.getDataset(active.code), [active.apiDataset, active.code, mode]);
  const updateById = useCallback((id: string, fn: (thread: ResearchThread) => ResearchThread) => {
    setThreads(list => list.map(thread => thread.id === id ? fn(thread) : thread));
  }, []);

  const refreshRun = useCallback(async (runId: string, targetId: string, signal?: AbortSignal) => {
    const result = await researchApi.getRunBundle(runId, signal);
    if (!result.ok) {
      if (result.error !== 'REQUEST_ABORTED') setApiError(result.error);
      return null;
    }
    setApiError(null);
    setThreads(list => {
      const existing = list.find(thread => thread.id === targetId);
      if (existing) return list.map(thread => thread.id === targetId ? applyBundle(thread, result.data) : thread);
      const restoredThread = applyBundle(createThread(targetId, '自定义研究', '', result.data.run.goal), result.data);
      return [restoredThread, ...list];
    });
    return result.data;
  }, []);

  useEffect(() => {
    if (mode !== 'api' || restored.current) return;
    const runId = window.localStorage.getItem('investment-x-buddy.active-run');
    if (!runId) return;
    const targetId = `api-${runId}`;
    const controller = new AbortController();
    const timer = window.setTimeout(() => { void refreshRun(runId, targetId, controller.signal).then(bundle => { if (!controller.signal.aborted) { restored.current = true; if (bundle) { setActiveId(targetId); setGoal(bundle.run.goal); } } }); }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [mode, refreshRun]);

  useEffect(() => {
    if (mode !== 'api' || !active.remoteRunId || !active.apiStatus || !pollable.has(active.apiStatus)) return;
    const controller = new AbortController();
    const tick = async () => {
      if (pollInFlight.current) return;
      pollInFlight.current = true;
      try { await refreshRun(active.remoteRunId!, active.id, controller.signal); } finally { pollInFlight.current = false; }
    };
    const timer = window.setInterval(() => void tick(), 1500);
    return () => { window.clearInterval(timer); controller.abort(); pollInFlight.current = false; };
  }, [active.apiStatus, active.id, active.remoteRunId, mode, refreshRun]);

  const dispatch = async (type: Exclude<RunAction['type'], 'START'>) => {
    if (mode === 'demo') {
      updateById(active.id, thread => transition(thread, { type, time: now() } as RunAction));
      return;
    }
    if (!active.remoteRunId) { setApiError('当前线程还没有真实 run_id。'); return; }
    if (!['APPROVE', 'REJECT', 'RESUME', 'CANCEL'].includes(type)) return;
    setApiError(null);
    updateById(active.id, thread => ({ ...thread, loading: true, status: type === 'APPROVE' || type === 'RESUME' ? 'running' : thread.status }));
    const controller = new AbortController();
    const allowedTools = [...new Set((active.tasks ?? []).map(task => task.toolName))];
    const result = type === 'APPROVE'
      ? await researchApi.approve(active.remoteRunId, active.planVersion ?? 0, allowedTools, controller.signal)
      : type === 'REJECT'
        ? await researchApi.reject(active.remoteRunId, active.planVersion ?? 0, 'Rejected by the user in the web workspace.', controller.signal)
        : type === 'RESUME'
          ? await researchApi.resume(active.remoteRunId, controller.signal)
          : await researchApi.cancel(active.remoteRunId, controller.signal);
    if (!result.ok) {
      setApiError(result.error);
      updateById(active.id, thread => ({ ...thread, loading: false, status: active.status }));
      return;
    }
    await refreshRun(active.remoteRunId, active.id);
  };

  const start = async () => {
    if (mode === 'demo') {
      updateById(active.id, thread => transition(thread, { type: 'START', goal }));
      return;
    }
    setApiError(null);
    updateById(active.id, thread => ({ ...thread, loading: true, status: 'running', goal }));
    const result = await researchApi.createRun(goal, preferences);
    if (!result.ok) {
      setApiError(result.error);
      updateById(active.id, thread => ({ ...thread, loading: false, status: 'failed' }));
      return;
    }
    window.localStorage.setItem('investment-x-buddy.active-run', result.data.id);
    const bundle = await refreshRun(result.data.id, active.id);
    updateById(active.id, thread => ({ ...thread, loading: false, tab: bundle ? 'Plan' : thread.tab }));
  };

  const selectThread = (id: string) => {
    const target = threads.find(thread => thread.id === id);
    if (!target) return;
    setActiveId(id); setGoal(target.goal); setSidebarOpen(false);
    if (mode === 'api' && target.remoteRunId) window.localStorage.setItem('investment-x-buddy.active-run', target.remoteRunId);
  };
  const newThread = () => {
    const id = `local-${Date.now()}`;
    const next = { ...createThread(id), ...(mode === 'api' ? { updated: '尚未创建研究', apiTools: active.apiTools ?? [] } : {}) };
    setThreads(list => [next, ...list]); setActiveId(id); setGoal(''); setSidebarOpen(false);
  };
  const setTab = (tab: WorkspaceTab) => updateById(active.id, thread => ({ ...thread, tab }));
  const selectedEvidence = mode === 'api' ? active.apiEvidence?.find(item => item.id === evidenceId) : evidence.find(item => item.id === evidenceId);

  return <main className="app-shell">
    <div className={`sidebar-backdrop ${sidebarOpen ? 'show' : ''}`} onClick={() => setSidebarOpen(false)} />
    <div className={sidebarOpen ? 'sidebar-wrap open' : 'sidebar-wrap'}><Sidebar threads={threads} active={active.id} onSelect={selectThread} onNew={newThread} onPreferences={() => setPrefsOpen(true)} onClose={() => setSidebarOpen(false)} /></div>
    <section className="workspace">
      <ResearchHeader thread={active} onMenu={() => setSidebarOpen(true)} mode={mode} />
      <div className="workspace-inner">
        <ResearchInput thread={active} goal={goal} setGoal={setGoal} onStart={start} />
        <nav className="tabs" aria-label="工作区标签">{([['Research', BarChart3], ['Plan', ListChecks], ['Trace', ScrollText]] as const).map(([tab, Icon]) => <button key={tab} data-testid={`tab-${tab.toLowerCase()}`} className={active.tab === tab ? 'active' : ''} onClick={() => setTab(tab)}><Icon />{tab}{tab === 'Plan' && active.status === 'approval' && <span className="tab-alert">1</span>}</button>)}</nav>
        <div className="tab-content">
          {active.tab === 'Research' && <><FinancialMetrics data={data} state={active.loading ? 'loading' : data ? 'ready' : 'empty'} /><FinancialCharts data={data} state={active.loading ? 'loading' : data ? 'ready' : 'empty'} /><ResearchReport thread={active} data={data} onEvidence={setEvidenceId} mode={mode} /></>}
          {active.tab === 'Plan' && <ResearchPlan thread={active} expanded={expanded} setExpanded={setExpanded} onAction={dispatch} mode={mode} />}
          {active.tab === 'Trace' && <ExecutionTrace thread={active} />}
        </div>
      </div>
    </section>
    <AgentMonitor thread={active} mode={mode} apiError={apiError} onOpenPreferences={() => setPrefsOpen(true)} onSwitchDemo={() => { setMode('demo'); setApiError(null); }} />
    <DetailDialog open={!!selectedEvidence} onOpenChange={open => !open && setEvidenceId(null)} title={`${selectedEvidence?.id ?? ''} · ${selectedEvidence?.title ?? ''}`} description={`${selectedEvidence?.type ?? ''} · ${selectedEvidence?.period ?? ''}`}><div className="dialog-copy"><strong>证据摘要</strong><pre className="evidence-json">{selectedEvidence?.detail}</pre><strong>限制</strong><p>{selectedEvidence?.limitation}</p><div className="demo-note">{(mode === 'demo' || (selectedEvidence && 'isDemo' in selectedEvidence && selectedEvidence.isDemo)) ? 'DEMO DATA · 此证据来自 Fixture 工具。' : 'FUYAO · 扶摇真实接口数据，时间以证据记录为准。'}</div></div></DetailDialog>
    <DetailDialog open={prefsOpen} onOpenChange={setPrefsOpen} title="Research Preferences" description={mode === 'api' ? '创建新 Run 时写入后端长期记忆' : 'Demo Mode 仅在本页面会话内保留'}><div className="preferences-form"><label>投资期限<select value={preferences.horizon} onChange={event => setPreferences(value => ({ ...value, horizon: event.target.value }))}><option>1 年以内</option><option>1–3 年</option><option>3–5 年</option><option>5 年以上</option></select></label><label>风险偏好<select value={preferences.risk} onChange={event => setPreferences(value => ({ ...value, risk: event.target.value }))}><option>保守</option><option>中等</option><option>进取</option></select></label><label className="check-row"><input type="checkbox" checked={preferences.evidence} onChange={event => setPreferences(value => ({ ...value, evidence: event.target.checked }))} />报告必须包含证据引用</label><div className="unavailable"><Server />{mode === 'api' ? '偏好将在创建 Run 时持久化' : '后端长期记忆：当前为本地演示'}</div></div></DetailDialog>
  </main>;
}
