'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, ListChecks, ScrollText, Server } from 'lucide-react';
import { Sidebar } from '@/components/sidebar';
import { ResearchHeader } from '@/components/research-header';
import { ResearchInput } from '@/components/research-input';
import { useDocumentConversation } from '@/components/document-conversation';
import { FinancialCharts, FinancialMetrics } from '@/components/financial-charts';
import { ResearchReport } from '@/components/research-report';
import { ResearchFollowup } from '@/components/research-followup';
import { EvidenceTable } from '@/components/research-evidence-table';
import { ResearchReview } from '@/components/research-review';
import { consumeResearchEvents } from '@/lib/research-stream';
import { ResearchPlan } from '@/components/research-plan';
import { ExecutionTrace } from '@/components/execution-trace';
import { AgentMonitor } from '@/components/agent-monitor';
import { DetailDialog } from '@/components/ui/dialog';
import { createThread, evidence, initialThreads } from '@/data/demo';
import { transition } from '@/lib/demo-machine';
import { identity, privateFetch } from '@/lib/identity';
import { applyBundle, configuredMode, demoGateway, researchApi, type AppMode } from '@/lib/research-gateway';
import type { Preferences, ResearchThread, RunAction, WorkspaceTab } from '@/types/research';

const now = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const pollable = new Set(['PLANNING', 'APPROVED', 'RUNNING']);

export function ResearchDashboard() {
  const [threads, setThreads] = useState<ResearchThread[]>(() => configuredMode === 'api' ? [{ ...createThread('api-draft', '研究工作台', '', '新的研究线程'), updated: '尚未创建研究', apiTools: [] }] : initialThreads);
  const [activeId, setActiveId] = useState(configuredMode === 'api' ? 'api-draft' : 'maotai');
  const active = threads.find(thread => thread.id === activeId) ?? threads[0];
  const documents = useDocumentConversation(activeId);
  const [goal, setGoal] = useState(active.goal);
  const mode: AppMode = configuredMode;
  const [apiError, setApiError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(0);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [preferences, setPreferences] = useState<Preferences>({ horizon: '3–5 年', risk: '中等', evidence: true });
  const pollInFlight = useRef(false);
  const restored = useRef(false);
  const eventCursors = useRef<Record<string, number>>({});

  useEffect(() => {
    if (mode !== 'api') return;
    let alive = true;
    void identity().then(async current => {
      if (current.user.kind !== 'account') return;
      const response = await privateFetch('/api/v1/auth/preferences');
      if (!response.ok) return;
      const saved = await response.json();
      if (alive) setPreferences(previous => ({horizon:saved.horizon || previous.horizon,risk:saved.risk || previous.risk,evidence:saved.evidence ?? previous.evidence}));
    }).catch(() => { /* Existing API error handling displays connection failures. */ });
    return () => { alive = false; };
  }, [mode]);

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
      if (existing) return list.map(thread => {
        if (thread.id !== targetId) return thread;
        const updated = applyBundle(thread, result.data);
        return thread.tab === 'Plan' && thread.status === 'running' && result.data.report
          && updated.status !== 'running' ? { ...updated, tab: 'Research' } : updated;
      });
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
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      void consumeResearchEvents(active.remoteRunId!, eventCursors.current[active.remoteRunId!] ?? 0, controller.signal, cursor => {
        eventCursors.current[active.remoteRunId!] = cursor;
        void tick();
      }).catch(() => { /* Polling remains available while streaming reconnects. */ }).finally(() => {
        if (!controller.signal.aborted) reconnect = setTimeout(connect, 3000);
      });
    };
    connect();
    return () => { window.clearInterval(timer); clearTimeout(reconnect); controller.abort(); pollInFlight.current = false; };
  }, [active.apiStatus, active.id, active.remoteRunId, mode, refreshRun]);

  const dispatch = async (type: Exclude<RunAction['type'], 'START'>) => {
    if (mode === 'demo') {
      updateById(active.id, thread => transition(thread, { type, time: now() } as RunAction));
      return;
    }
    if (active.loading) return;
    if (!active.remoteRunId) { setApiError('当前线程还没有真实 run_id。'); return; }
    if (!['APPROVE', 'REJECT', 'RESUME', 'CANCEL', 'RETRY_FAILED'].includes(type)) return;
    setApiError(null);
    updateById(active.id, thread => ({ ...thread, loading: true, status: type === 'APPROVE' || type === 'RESUME' || type === 'RETRY_FAILED' ? 'running' : thread.status }));
    const controller = new AbortController();
    const allowedTools = [...new Set((active.tasks ?? []).map(task => task.toolName))];
    const result = type === 'APPROVE'
      ? await researchApi.approve(active.remoteRunId, active.planVersion ?? 0, allowedTools, controller.signal)
      : type === 'REJECT'
        ? await researchApi.reject(active.remoteRunId, active.planVersion ?? 0, 'Rejected by the user in the web workspace.', controller.signal)
        : type === 'RETRY_FAILED'
          ? await researchApi.retryFailed(active.remoteRunId, active.planVersion ?? 0, active.remoteUpdatedAt ?? '', controller.signal)
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
    const researchGoal = goal;
    if (documents.hasDocuments) {
      setTab('Research');
      await documents.send(goal);
      return;
    }
    if (mode === 'demo') {
      updateById(active.id, thread => transition(thread, { type: 'START', goal }));
      return;
    }
    setApiError(null);
    updateById(active.id, thread => ({ ...thread, loading: true, status: 'running', goal: researchGoal }));
    const result = await researchApi.createRun(researchGoal, preferences);
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
  const revisePlan = async (nextGoal: string, excludedTools: string[], feedback?: string, fiscalYear?: number) => {
    if (!active.remoteRunId || !active.planVersion || !active.remoteUpdatedAt) return { message: '请刷新计划后再试。', error: true };
    updateById(active.id, thread => ({ ...thread, loading: true }));
    try {
      const result = await researchApi.revisePlan(active.remoteRunId, active.planVersion, active.remoteUpdatedAt, nextGoal, excludedTools, feedback, fiscalYear);
      if (!result.ok) return { message: result.error, error: true };
      if ('clarification' in result.data) return { message: result.data.clarification, error: false, planUnchanged: true };
      if (!await refreshRun(active.remoteRunId, active.id)) return { message: '新版已保存，请刷新查看。', error: false };
      setExpanded(null);
      return null;
    } finally {
      updateById(active.id, thread => ({ ...thread, loading: false }));
    }
  };
  const apiEvidence = mode === 'api' ? active.apiEvidence?.find(item => item.id === evidenceId) : undefined;
  const selectedEvidence = mode === 'api' ? apiEvidence : evidence.find(item => item.id === evidenceId);

  const viewingReport = mode === 'api' && !documents.hasDocuments && active.tab === 'Research' && !!active.apiReport;
  const canFollowup = mode === 'api' && !!active.apiReport && ['COMPLETE', 'PARTIAL', 'FAILED'].includes(active.apiStatus ?? '');
  const tabLabels = { Research: '研究报告', Plan: '研究计划', Trace: '运行详情' };
  const input = <ResearchInput thread={active} goal={goal} setGoal={setGoal} onStart={() => void start()}
    documentMode={documents.hasDocuments}
    busy={documents.busy}>{documents.controls}</ResearchInput>;

  return <main className="app-shell answer-workspace">
    <div className={`sidebar-backdrop ${sidebarOpen ? 'show' : ''}`} onClick={() => setSidebarOpen(false)} />
    <div className={sidebarOpen ? 'sidebar-wrap open' : 'sidebar-wrap'}><Sidebar threads={threads} active={active.id} onSelect={selectThread} onNew={newThread} onPreferences={() => setPrefsOpen(true)} onClose={() => setSidebarOpen(false)} /></div>
    <section className="workspace">
      <ResearchHeader thread={active} onMenu={() => setSidebarOpen(true)} mode={mode} />
      <div className={canFollowup && viewingReport ? 'workspace-inner with-followup' : 'workspace-inner'}>
        {!viewingReport && (!active.apiReport || documents.hasDocuments) && input}
        <nav className="tabs" aria-label="工作区标签">{([['Research', BarChart3], ['Plan', ListChecks], ['Trace', ScrollText]] as const).filter(([tab])=>!documents.hasDocuments||tab==='Research').map(([tab, Icon]) => <button key={tab} data-testid={`tab-${tab.toLowerCase()}`} className={(documents.hasDocuments||active.tab === tab) ? 'active' : ''} onClick={() => setTab(tab)}><Icon />{documents.hasDocuments ? '资料对话' : tabLabels[tab]}{tab === 'Plan' && active.status === 'approval' && <span className="tab-alert">待确认</span>}</button>)}</nav>
        {apiError && active.tab !== 'Trace' && <p role="alert" className="my-3 text-sm text-red-700">{apiError}</p>}
        <div className="tab-content" id={viewingReport ? 'research-report-start' : undefined}>
          {(active.tab === 'Research' || documents.hasDocuments) && <>
            {documents.messages}
            {!documents.hasDocuments && <>
              <ResearchReport thread={active} data={data} onEvidence={setEvidenceId} mode={mode} review={mode === 'api' && active.plannerMode !== 'periodic_filing' &&
                <ResearchReview key={active.remoteRunId ?? active.id} thread={active}
                  onRefresh={() => active.remoteRunId ? refreshRun(active.remoteRunId, active.id) : Promise.resolve()} />} />
              {data && <details className="card chart-disclosure">
                <summary>查看行情与财务图表</summary>
                <FinancialMetrics data={data} state="ready" />
                <FinancialCharts data={data} state="ready" />
              </details>}
            </>}
          </>}
          {!documents.hasDocuments&&active.tab === 'Plan' && <ResearchPlan thread={active} expanded={expanded} setExpanded={setExpanded} onAction={dispatch} onRevise={revisePlan} mode={mode} />}
          {!documents.hasDocuments && active.tab === 'Trace' && <div className="run-details">
            <ExecutionTrace thread={active} />
            <AgentMonitor thread={active} mode={mode} apiError={apiError} onOpenPreferences={() => setPrefsOpen(true)} />
          </div>}
        </div>
        {canFollowup && !documents.hasDocuments && <ResearchFollowup key={active.remoteRunId ?? active.id}
            visible={viewingReport} thread={active} />}
      </div>
    </section>
    <DetailDialog open={!!selectedEvidence} onOpenChange={open => !open && setEvidenceId(null)} title={`${selectedEvidence?.id ?? ''} · ${selectedEvidence?.title ?? ''}`} description={`${selectedEvidence?.type ?? ''} · ${selectedEvidence?.period ?? ''}`}>
      {selectedEvidence && <div className="dialog-copy">
        {apiEvidence ? <EvidenceTable item={apiEvidence} /> : <pre className="evidence-json">{selectedEvidence.detail}</pre>}
        <strong>证据限制</strong><p>{selectedEvidence.limitation}</p>
      </div>}
    </DetailDialog>
    <DetailDialog open={prefsOpen} onOpenChange={setPrefsOpen} title="Research Preferences" description={mode === 'api' ? '创建新 Run 时写入后端长期记忆' : 'Demo Mode 仅在本页面会话内保留'}><div className="preferences-form"><label>投资期限<select value={preferences.horizon} onChange={event => setPreferences(value => ({ ...value, horizon: event.target.value }))}><option>1 年以内</option><option>1–3 年</option><option>3–5 年</option><option>5 年以上</option></select></label><label>风险偏好<select value={preferences.risk} onChange={event => setPreferences(value => ({ ...value, risk: event.target.value }))}><option>保守</option><option>中等</option><option>进取</option></select></label><label className="check-row"><input type="checkbox" checked={preferences.evidence} onChange={event => setPreferences(value => ({ ...value, evidence: event.target.checked }))} />报告必须包含证据引用</label><div className="unavailable"><Server />{mode === 'api' ? '偏好将在创建 Run 时持久化' : '后端长期记忆：当前为本地演示'}</div></div></DetailDialog>
  </main>;
}
