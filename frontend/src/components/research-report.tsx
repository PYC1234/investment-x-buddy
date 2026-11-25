import type { ReactNode } from "react";
import type { ResearchEvidence } from "@/types/research";
import { ArrowUpRight, BookOpen, CircleCheck, FileText, ShieldAlert } from 'lucide-react';
import { evidence as demoEvidence } from '@/data/demo';
import type { AppMode } from '@/lib/research-gateway';
import type { Dataset, ResearchThread } from '@/types/research';
import { ProfitabilityTable } from '@/components/research-evidence-table';

function groupLimitations(messages: string[]) {
  const groups = new Map<string, Set<string>>();
  for (const item of messages) {
    const match = /^\[(EVD-[A-Z0-9]+)\]\s+(.+)$/.exec(item);
    let message = match?.[2] ?? item;
    if (message === '仅作接口级质量检查，未与交易所公告或独立来源交叉核验。'
        || message === '扶摇接口数据尚未与交易所原始公告交叉核验。') {
      message = '扶摇数据已接受接口级检查，尚待独立来源交叉核验。';
    }
    const ids = groups.get(message) ?? new Set<string>();
    if (match) ids.add(match[1]);
    groups.set(message, ids);
  }
  return [...groups].map(([message, ids]) => ({ message, ids: [...ids] }));
}

export function ResearchReport({ thread, data, onEvidence, mode, review }: { thread: ResearchThread; data: Dataset | null; onEvidence: (id: string) => void; mode: AppMode; review?: ReactNode }) {
  if (mode === 'api') {
    const report = thread.apiReport;
    const evidence = thread.apiEvidence ?? [];
    const evidenceById = new Map(evidence.map(item => [item.id, item]));
    const coverage = report?.review?.coverage_status === 'SCOPED_EVIDENCE_COLLECTED';
    const annualGaps = report?.annualAnswers?.some(answer => answer.status.startsWith('MISSING'));
    const limitations = groupLimitations(report?.missingInformation ?? []);
    const income = thread.researchScope?.type === 'profitability' ? evidence.find(item =>
      item.toolName === 'get_financial_summary' && !item.isDemo
      && (item.data.quality as { usable?: boolean } | undefined)?.usable !== false) : undefined;
    return <section className="card report">
      <div className="card-heading">
        <h2><FileText size={17} />研究报告 <span>Research Report</span></h2>
        <span className="report-version">{report ? (annualGaps || !coverage ? '有待核实的问题' : '已收集所需证据类别') : '等待执行'}</span>
      </div>
      {!report ? <div className="report-empty"><BookOpen size={24} />
        <p>{thread.loading ? '后端正在执行研究计划…' : '完成审批和执行后生成报告。'}</p>
      </div> : <>
        <div className="report-intro">
          <h3>{report.title}</h3><p>{report.executiveSummary}</p><p>{report.dataNotice}</p>
          <p>证据检查：{report.qualityStatus === 'FAIL' ? '有证据未通过检查' : report.qualityStatus === 'WARN' ? '有核验提示，详见各条证据' : report.qualityStatus === 'PASS' ? '基础检查通过' : '未完成统一检查'}</p>
        </div>
        <div className="report-body">
          <div>
            <h4><CircleCheck size={15} className="text-emerald-600" />核心发现</h4>
            {income && <ProfitabilityTable item={income} onOpen={() => onEvidence(income.id)} />}
            <div className="grid gap-4">
              {report.findings.map((finding, index) => <article key={`${finding.task}-${index}`} className="rounded border p-3">
                <h5 className="font-semibold">{finding.task}</h5>
                <p className="mt-1">{finding.statement}</p>
                {finding.evidenceIds.length === 0 && <p className="mt-2 text-sm text-amber-800">待补资料 · 暂无直接证据</p>}
                {finding.evidenceIds.map(id => {
                  const item = evidenceById.get(id);
                  return item ? <FindingEvidence key={id} item={item} onOpen={() => onEvidence(id)} showExcerpts={!report.annualAnswers} />
                    : <p key={id} className="mt-2 text-sm text-amber-800">引用暂不可读取</p>;
                })}
              </article>)}
            </div>
          </div>
          <div className="risk-box">
            <h4><ShieldAlert size={15} />缺失信息与限制</h4>
            {limitations.length ? limitations.map(({ message, ids }) => <div key={message} className="mb-2">
              <p>{message}</p>
              {ids.map(id => evidenceById.has(id) && <button key={id} type="button" className="citation mr-1 text-xs"
                onClick={() => onEvidence(id)} aria-label={`查看证据 ${id}`}>{id}</button>)}
            </div>) : <p>暂无额外缺失信息。</p>}
            {review}
          </div>
        </div>
        {report.annualAnswers && <section className="evidence-footer" aria-label="财报原文与页码">
          <h4><BookOpen size={15} />财报原文与页码</h4>
          {report.annualAnswers.map(answer => <div key={answer.label} className="mt-3 rounded border p-3 text-sm">
            <strong>{answer.label}</strong> · {answerStatus[answer.status]}
            {answer.excerpt_refs?.length ? answer.excerpt_refs.map(ref => {
              const item = evidenceById.get(ref.evidence_id);
              return item && <FindingEvidence key={`${item.id}-${ref.record_index}`} item={item}
                recordIndex={ref.record_index} onOpen={() => onEvidence(item.id)} />;
            }) : answer.evidence_ids.map(id => <button key={id} className="citation ml-2" onClick={() => onEvidence(id)}>查看对应证据</button>)}
          </div>)}
        </section>}
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
    return ['https:', 'http:'].includes(url.protocol) && url.hostname !== 'fuyao.aicubes.cn' ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function FindingEvidence({ item, onOpen, recordIndex, showExcerpts = true }: {
  item: ResearchEvidence; onOpen: () => void; recordIndex?: number; showExcerpts?: boolean;
}) {
  const quality = item.data.quality as { status?: string; usable?: boolean; issues?: { code: string }[] } | undefined;
  const isFuyao = item.data.data_label === 'FUYAO / MARKET DATA';
  const source = !isFuyao && (item.data.dataset !== 'filings'
    || (item.toolName === 'find_official_annual_report' && Array.isArray(item.data.records) && item.data.records.length === 0))
    ? sourceUrl(item.data.source) : undefined;
  const fields = Object.values((item.data.field_provenance ?? {}) as Record<string, { basis?: string; unit?: string }>);
  const bases = [...new Set(fields.map(field => [field.basis, field.unit].filter(Boolean).join(' · ')))].filter(Boolean);
  const excerpts = showExcerpts && item.data.dataset === 'filings' && Array.isArray(item.data.records)
    ? (item.data.records as Array<{ title: string; source?: string; page: number; basis: string; text: string }>)
      .filter((_, index) => recordIndex === undefined || recordIndex === index)
    : [];
  return <div className="mt-3 border-t pt-2 text-sm">
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <button className="citation" onClick={onOpen}>{item.title} · 查看证据</button>
      <span>{item.isDemo ? 'DEMO DATA' : isFuyao ? '来源：扶摇数据接口' : String(item.data.data_label ?? '来源见证据')} · {item.period}</span>
      {quality?.status === 'WARN' && <span className="text-amber-800">
        {quality.issues?.length === 1 && quality.issues[0].code === 'SOURCE_NOT_CROSS_CHECKED' ? '未独立交叉核验' : '有核验提示'}
      </span>}
      {quality?.usable === false && <span className="text-amber-800">已排除</span>}
    </div>
    {isFuyao && <p className="mt-1 text-slate-600">在「查看证据」中核对本次取数的数值、时间与口径。</p>}
    {source && <a className="underline" href={source} target="_blank" rel="noreferrer">打开公开来源</a>}
    {bases.length > 0 && <p className="mt-1 text-slate-600">口径：{bases.join('；')}</p>}
    {excerpts.map((row, index) => {
      const url = sourceUrl(row.source);
      if (Number.isInteger(row.page) && row.page > 0) {
        const link = url ? new URL(url) : undefined;
        if (link) link.hash = `page=${row.page}`;
        return <div key={index} className="mt-2 rounded bg-slate-50 p-2">
          <p>{row.title} · 第 {row.page} 页</p>
          {link ? <a className="underline" href={link.href} target="_blank" rel="noreferrer">打开财报原文</a>
            : <p>来源：本次上传的 PDF。请按页码核对。</p>}
          <details className="mt-1">
            <summary className="cursor-pointer">展开引用</summary>
            <blockquote className="my-2 whitespace-pre-wrap">{row.text}</blockquote>
            <p>{row.basis}</p>
          </details>
        </div>;
      }
      return null;
    })}
  </div>;
}
