'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { FindingContent } from '@/components/research-report';
import { createThread } from '@/data/demo';
import { applyBundle, researchApi } from '@/lib/research-gateway';
import type { ResearchThread } from '@/types/research';

const running = new Set(['PLANNING', 'APPROVED', 'RUNNING']);

export function FollowupResearch({ runId, onUpdate }: {
  runId: string; onUpdate: (run: ResearchThread) => void;
}) {
  const [run, setRun] = useState<ResearchThread>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      const result = await researchApi.getRunBundle(runId, controller.signal);
      if (controller.signal.aborted) return;
      if (!result.ok) {
        setError(result.error);
        return;
      }
      const updated = applyBundle(createThread(runId), result.data);
      setRun(updated);
      setError('');
      onUpdate(updated);
      if (running.has(updated.apiStatus ?? '')) timer = setTimeout(() => void load(), 1500);
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [runId, onUpdate, reload]);

  async function act(action: 'approve' | 'reject' | 'cancel' | 'retry') {
    if (!run || busy) return;
    setBusy(true);
    setError('');
    try {
      const version = run.planVersion ?? 0;
      const result = action === 'approve' ? await researchApi.approve(runId, version, [...new Set(run.tasks?.map(task => task.toolName))])
        : action === 'reject' ? await researchApi.reject(runId, version, '用户拒绝补查计划。')
        : action === 'retry' ? await researchApi.retryFailed(runId, version, run.remoteUpdatedAt ?? '')
        : await researchApi.cancel(runId);
      if (!result.ok) setError(result.error);
      else setReload(current => current + 1);
    } finally {
      setBusy(false);
    }
  }

  const evidence = new Map(run?.apiEvidence?.map(item => [item.id, item]));
  const working = running.has(run?.apiStatus ?? '');
  const canRetry = Boolean(run?.apiReport && run.tasks?.some(task => task.status === 'FAILED') && run.approval === 'approved');
  return <section className="followup-research mt-3 rounded-lg border p-3" aria-label="补查">
    {error && <p role="alert" className="mb-2 text-sm text-red-700">{error}
      <button type="button" className="ml-2 underline" onClick={() => setReload(current => current + 1)}>刷新进度</button>
    </p>}
    {!run && !error && <p role="status">正在加载补查计划…</p>}
    {run?.status === 'approval' && <div className="space-y-2 text-sm">
      <h4 className="font-semibold">补查计划</h4>
      <p>{run.researchScope?.scope.join(' · ') || run.goal}</p>
      <ul className="list-disc pl-5">{run.tasks?.map(task => <li key={task.id}>{task.title}</li>)}</ul>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy} onClick={() => void act('approve')}>批准补查</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void act('reject')}>拒绝补查</Button>
      </div>
    </div>}
    {working && <div className="flex items-center justify-between gap-2 text-sm">
      <p role="status">正在补查资料…</p>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => void act('cancel')}>停止</Button>
    </div>}
    {run?.status === 'rejected' && <p className="text-sm">补查计划已拒绝。</p>}
    {run?.status === 'cancelled' && <p className="text-sm">补查已停止。</p>}
    {run?.apiReport && !working && run.status !== 'approval' && <div className="space-y-3">
      <h4 className="font-semibold">补查结果</h4>
      {run.apiReport.period && <p className="text-sm text-slate-600">{run.apiReport.period}</p>}
      {run.apiReport.findings.map((finding, index) => <div key={index}>
        <h5 className="text-sm font-medium">{finding.task}</h5>
        <FindingContent finding={finding} evidence={evidence} />
      </div>)}
      {run.apiReport.findings.length === 0 && <p className="text-sm">{run.apiReport.executiveSummary}</p>}
      {canRetry && <Button size="sm" variant="outline" disabled={busy} onClick={() => void act('retry')}>重试失败任务</Button>}
    </div>}
    {run?.status === 'failed' && !run.apiReport && <p className="text-sm">补查失败。{run.tasks?.find(task => task.error)?.error}</p>}
  </section>;
}
