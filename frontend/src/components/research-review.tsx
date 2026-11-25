'use client';
import { useState } from 'react';
import { researchApi } from '@/lib/research-gateway';
import type { ResearchThread } from '@/types/research';

export function ResearchReview({ thread, onRefresh }: { thread: ResearchThread; onRefresh: () => Promise<unknown> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pdf, setPdf] = useState<File>();
  const [confirmed, setConfirmed] = useState(false);
  const [offset, setOffset] = useState(0);
  const report = thread.apiReport;
  if (!report?.review) return null;
  const review = report.review;
  const canSupplement = review.missing_evidence.length > 0 && ['COMPLETE', 'PARTIAL'].includes(thread.apiStatus ?? '') && review.supplement_rounds < review.max_supplement_rounds;
  const canUpload = Boolean(report.annualAnswers && report.annualAnswers.some(answer => answer.status === 'MISSING_EXPLANATION')
    && ['COMPLETE', 'PARTIAL'].includes(thread.apiStatus ?? '') && review.supplement_rounds < review.max_supplement_rounds);
  const upload = async () => {
    if (!pdf || !confirmed || !thread.remoteRunId || busy) return;
    if (pdf.size > 3 * 1024 * 1024) { setError('PDF 不得超过 3 MB，请截取相关章节。'); return; }
    setBusy(true);
    setError('');
    try {
      const bytes = new Uint8Array(await pdf.arrayBuffer());
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 8192) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      }
      const result = await researchApi.attachAnnualReport(thread.remoteRunId, {
        filename: pdf.name, content_base64: btoa(binary), confirmed, page_offset: offset,
        plan_version: thread.planVersion ?? 0, expected_updated_at: thread.remoteUpdatedAt ?? '',
      });
      if (!result.ok) setError(result.error);
      else {
        setPdf(undefined);
        setConfirmed(false);
        setOffset(0);
        await onRefresh();
      }
    } catch { setError('上传未完成，请重试。'); }
    finally { setBusy(false); }
  };
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
  return <section className="mt-4 border-t pt-3" aria-label="研究覆盖检查">
    <h2 className="font-semibold mb-3">研究覆盖与结论检查</h2>
    {thread.status === 'approval' && <p className="text-xs text-slate-500 mb-2">以下为上一轮已完成研究的检查结果；新版计划尚未执行。</p>}
    <p className="text-sm">{!report.annualAnswers && (review.coverage_status === 'LIMITED' ? '当前证据覆盖有限 · ' : '已收集所需证据类别 · ')}补充研究 {review.supplement_rounds}/{review.max_supplement_rounds} 轮。</p>
    {review.missing_evidence.length > 0 && <p className="text-sm mt-2">待补充：{review.missing_evidence.join('、')}</p>}
    {thread.status === 'approval' && <p className="text-sm mt-3 text-amber-800">发现可补充的资料，已生成新版计划。请前往 Plan 核对并批准；已有成功证据会保留。</p>}
    {canSupplement && <button className="mt-3 rounded border px-3 py-2 text-sm" disabled={busy} onClick={() => void requestSupplement()}>{busy ? '检查中…' : '检查可补充资料'}</button>}
    {canUpload && <details className="mt-3 rounded border p-2 text-sm">
      <summary className="cursor-pointer">上传年报 PDF 补查</summary>
      <form className="mt-2 grid gap-2" onSubmit={event => { event.preventDefault(); void upload(); }}>
        <p>{thread.goal} · 支持 3 MB 以内的可复制文字 PDF，可上传相关章节。</p>
        <input aria-label="年度报告 PDF" type="file" accept=".pdf,application/pdf" disabled={busy} onChange={event => {
          setPdf(event.target.files?.[0]); setConfirmed(false); setError('');
        }} />
        <label>节选前省略的页数 <input type="number" min={0} max={1000} step={1} value={offset}
          disabled={busy} onChange={event => setOffset(Number(event.target.value))} className="w-20 rounded border px-2" /></label>
        <label className="flex items-start gap-2"><input type="checkbox" checked={confirmed} disabled={busy || !pdf}
          onChange={event => setConfirmed(event.target.checked)} />我确认 PDF 对应本次研究的公司和财年</label>
        <button type="submit" className="justify-self-start rounded border px-3 py-2" disabled={!pdf || !confirmed || busy}>
          {busy ? '读取中…' : '生成补查计划'}
        </button>
      </form>
    </details>}
    {error && <p role="status" className="text-sm mt-2 text-amber-800">{error}</p>}
    {report.validation && <p className="text-xs mt-3">字段与计算检查：{report.validation.status === 'RULE_CHECKED' ? '已按规则核对' : '发现需复核的问题'} · {report.validation.checked_claims} 项；自然语言推断未独立验证。</p>}
    <p className="text-xs text-slate-500 mt-2">{review.policy}</p>
  </section>;
}
