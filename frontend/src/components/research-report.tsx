import type { ReactNode } from "react";
import type { ResearchEvidence } from "@/types/research";
import { ArrowUpRight, BookOpen, CircleCheck, FileText, ShieldAlert } from 'lucide-react';
import { evidence as demoEvidence } from '@/data/demo';
import type { AppMode } from '@/lib/research-gateway';
import type { Dataset, ResearchThread } from '@/types/research';

export function ResearchReport({ thread, data, onEvidence, mode, review }: { thread: ResearchThread; data: Dataset | null; onEvidence: (id: string) => void; mode: AppMode; review?: ReactNode }) {
  if (mode === 'api') {
    const report = thread.apiReport;
    const evidence = thread.apiEvidence ?? [];
    const evidenceById = new Map(evidence.map(item => [item.id, item]));
    const coverage = report?.review?.coverage_status === 'SCOPED_EVIDENCE_COLLECTED';
    const annualGaps = report?.annualAnswers?.some(answer => answer.status.startsWith('MISSING'));
    return <section className="card report">
      <div className="card-heading">
        <h2><FileText size={17} />研究报告 <span>Research Report</span></h2>
        <span className="report-version">{report ? (report.annualAnswers ? (annualGaps ? '有待核实的问题' : '各问题均有证据') : coverage ? '已收集所需证据类别' : '证据覆盖有限') : '等待执行'}</span>
      </div>
      {!report ? <div className="report-empty"><BookOpen size={24} />
        <p>{thread.loading ? '后端正在执行研究计划…' : '完成审批和执行后生成报告。'}</p>
      </div> : <>
        <div className="report-intro">
          <h3>{report.title}</h3><p>{report.executiveSummary}</p><p>{report.dataNotice}</p>
          <p>证据质量：{report.qualityStatus === 'FAIL' ? '有证据未通过检查' : report.qualityStatus === 'WARN' ? '有证据需复核' : report.qualityStatus === 'PASS' ? '基础检查通过' : '未完成统一检查'}</p>
        </div>
        <div className="report-body">
          <div>
            {report.annualAnswers && <section className="mb-4 rounded border p-3" aria-label="财报问题与证据">
              <h4>财报问题与证据</h4>
              {report.annualAnswers.map(answer => <div key={answer.label} className="mt-2 text-sm">
                <strong>{answer.label}</strong> · {answerStatus[answer.status]}
                {answer.excerpt_refs?.length ? answer.excerpt_refs.map(ref => {
                  const item = evidenceById.get(ref.evidence_id);
                  return item && <FindingEvidence key={`${item.id}-${ref.record_index}`} item={item}
                    recordIndex={ref.record_index} onOpen={() => onEvidence(item.id)} />;
                }) : answer.evidence_ids.map(id => <button key={id} className="citation ml-2" onClick={() => onEvidence(id)}>查看对应证据</button>)}
              </div>)}
            </section>}
            <h4><CircleCheck size={15} className="text-emerald-600" />核心发现</h4>
            <div className="grid gap-4">
              {report.findings.map((finding, index) => <article key={`${finding.task}-${index}`} className="rounded border p-3">
                <h5 className="font-semibold">{finding.task}</h5>
                <p className="mt-1">{finding.statement}</p>
                {finding.evidenceIds.length === 0 && <p className="mt-2 text-sm text-amber-800">待补资料 · 暂无直接证据</p>}
                {finding.evidenceIds.map(id => {
                  const item = evidenceById.get(id);
                  return item ? <FindingEvidence key={id} item={item} onOpen={() => onEvidence(id)} />
                    : <p key={id} className="mt-2 text-sm text-amber-800">引用暂不可读取</p>;
                })}
              </article>)}
            </div>
          </div>
          <div className="risk-box">
            <h4><ShieldAlert size={15} />缺失信息与限制</h4>
            {report.missingInformation.length ? [...new Set(report.missingInformation)].map(item => <p key={item}>{item}</p>) : <p>暂无额外缺失信息。</p>}
            {review}
          </div>
        </div>
      </>}
      <footer className="report-footnote">证据需结合原文核对 · 不构成投资建议</footer>
    </section>;
  }
  const available = thread.step >= 2 && data;
  const completed = thread.status === 'completed';
  return <section className="card report"><div className="card-heading"><h2><FileText size={17} />研究报告 <span>Research Report</span></h2><span className="report-version">{completed ? '演示报告 v1.0' : '预览草稿'}</span></div>{!available ? <div className="report-empty"><BookOpen size={24} /><p>从一个问题，开始你的研究。</p><small>{thread.status === 'cancelled' ? '本次研究已取消，可重新开始。' : '开始研究并完成数据整理后，此处显示演示报告。'}</small></div> : <><div className="report-intro"><span className="eyebrow">RESEARCH SUMMARY</span><h3>{thread.company}：从盈利质量到估值合理性</h3><p>以下内容基于人工构造的本地样本，仅演示研究报告的组织方式。{!completed && '研究尚未完成，当前内容为示例预览。'}</p></div><div className="report-body"><div><h4><CircleCheck size={15} className="text-emerald-600" />核心发现 <span>Key Findings</span></h4><div className="findings">{data.findings.map((finding, index) => <div key={finding}><span className="finding-number">0{index + 1}</span><p>{finding} <button className="citation" onClick={() => onEvidence(index === 2 ? 'E02' : 'E01')}>[{index === 2 ? '2' : '1'}]</button></p></div>)}</div></div><div className="risk-box"><h4><ShieldAlert size={15} />风险与不确定性</h4><p>样本缺少真实公告与交叉验证，不能支持投资判断。</p><span>证据覆盖：仅演示样本</span></div></div><div className="evidence-footer"><h4>证据引用 <span>Evidence References</span></h4><div className="evidence-links">{demoEvidence.map((item, index) => <button key={item.id} onClick={() => onEvidence(item.id)}><span className="evidence-index">0{index + 1}</span><span>{item.title}<small>本地示例 · {item.id}</small></span><ArrowUpRight size={14} /></button>)}</div></div></>}<footer className="report-footnote">来源：frontend 本地演示数据集 · DEMO DATA · 不构成投资建议</footer></section>;
}

const answerStatus = {
  SUPPORTED: '有证据', DIRECT_EXCERPT: '找到直接说明，需核对上下文',
  MISSING_DATA: '缺当年数据', MISSING_COMPARISON: '缺上年对照',
  MISSING_EXPLANATION: '未找到直接解释',
} as const;

function sourceUrl(value: unknown) {
  if (typeof value !== 'string') return undefined;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function FindingEvidence({ item, onOpen, recordIndex }: { item: ResearchEvidence; onOpen: () => void; recordIndex?: number }) {
  const quality = item.data.quality as { status?: string; usable?: boolean } | undefined;
  const source = sourceUrl(item.data.source);
  const fields = Object.values((item.data.field_provenance ?? {}) as Record<string, { basis?: string; unit?: string }>);
  const bases = [...new Set(fields.map(field => [field.basis, field.unit].filter(Boolean).join(' · ')))].filter(Boolean);
  const excerpts = item.data.dataset === 'filings' && Array.isArray(item.data.records)
    ? (item.data.records as Array<{ title: string; source?: string; page: number; basis: string; text: string }>)
      .filter((_, index) => recordIndex === undefined || recordIndex === index)
    : [];
  return <div className="mt-3 border-t pt-2 text-sm">
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <button className="citation" onClick={onOpen}>{item.title} · 查看证据</button>
      <span>{item.isDemo ? 'DEMO DATA' : String(item.data.data_label ?? '来源见证据')} · {item.period}</span>
      {quality?.status === 'WARN' && <span className="text-amber-800">需复核</span>}
      {quality?.usable === false && <span className="text-amber-800">已排除</span>}
    </div>
    {source && !excerpts.length && <a className="underline" href={source} target="_blank" rel="noreferrer">数据来源</a>}
    {bases.length > 0 && <p className="mt-1 text-slate-600">口径：{bases.join('；')}</p>}
    {excerpts.map((row, index) => {
      const url = sourceUrl(row.source);
      if (Number.isInteger(row.page) && row.page > 0) {
        const link = url ? new URL(url) : undefined;
        if (link) link.hash = `page=${row.page}`;
        return <details key={index} className="mt-2 rounded bg-slate-50 p-2">
          <summary className="cursor-pointer">{row.title} · 第 {row.page} 页</summary>
          <blockquote className="my-2 whitespace-pre-wrap">{row.text}</blockquote>
          <p>{row.basis}</p>
          {link ? <a className="underline" href={link.href} target="_blank" rel="noreferrer">打开来源原文</a>
            : <p>请打开上传的 PDF 并核对标注页码。</p>}
        </details>;
      }
      return null;
    })}
  </div>;
}
