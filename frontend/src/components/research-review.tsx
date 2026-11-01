'use client';
import { useState } from 'react';
import { researchApi } from '@/lib/research-gateway';
import type { ResearchThread } from '@/types/research';

export function ResearchReview({ thread, onRefresh }: { thread: ResearchThread; onRefresh: () => Promise<unknown> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const report = thread.apiReport;
  if (!report?.review) return null;
  const review = report.review;
  const canSupplement = review.missing_evidence.length > 0 && ['COMPLETE', 'PARTIAL'].includes(thread.apiStatus ?? '') && review.supplement_rounds < review.max_supplement_rounds;
  const requestSupplement = async () => {
    if (!thread.remoteRunId || busy) return;
    setBusy(true); setError('');
    try {
      const result = await researchApi.supplement(thread.remoteRunId, thread.planVersion ?? 0, thread.remoteUpdatedAt ?? '');
      if (!result.ok) setError(result.error);
      else if (result.data.status !== 'PENDING_APPROVAL') setError('暂无可追加的数据来源，或本次执行预算已用完。导入资料后可再次检查。');
      await onRefresh();
    } catch { setError('检查失败，请稍后重试。'); }
    finally { setBusy(false); }
  };
  return <section className="card p-5 my-4" aria-label="研究覆盖检查">
    <h2 className="font-semibold mb-3">研究覆盖与结论检查</h2>
    {thread.status === 'approval' && <p className="text-xs text-slate-500 mb-2">以下为上一轮已完成研究的检查结果；新版计划尚未执行。</p>}
    <p className="text-sm">{review.coverage_status === 'LIMITED' ? '当前证据覆盖有限' : '已收集本次检查清单要求的证据类别'}；补充研究 {review.supplement_rounds}/{review.max_supplement_rounds} 轮。</p>
    {review.missing_evidence.length > 0 && <p className="text-sm mt-2">待补充：{review.missing_evidence.join('、')}</p>}
    {thread.status === 'approval' && <p className="text-sm mt-3 text-amber-800">发现可补充的资料，已生成新版计划。请前往 Plan 核对并批准；已有成功证据会保留。</p>}
    {canSupplement && <button className="mt-3 rounded border px-3 py-2 text-sm" disabled={busy} onClick={() => void requestSupplement()}>{busy ? '检查中…' : '检查可补充资料'}</button>}
    {error && <p role="status" className="text-sm mt-2 text-amber-800">{error}</p>}
    {report.validation && <p className="text-xs mt-3">字段与计算检查：{report.validation.status === 'RULE_CHECKED' ? '已按规则核对' : '发现需复核的问题'} · {report.validation.checked_claims} 项；自然语言推断未独立验证。</p>}
    <p className="text-xs text-slate-500 mt-2">{review.policy}</p>
  </section>;
}
