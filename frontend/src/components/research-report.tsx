'use client';

import { useState, type ReactNode } from "react";
import type { FilingComparison, ResearchEvidence, ResearchFinding } from "@/types/research";
import { ArrowUpRight, BookOpen, CircleCheck, FileText, ShieldAlert } from 'lucide-react';
import { evidence as demoEvidence } from '@/data/demo';
import type { AppMode } from '@/lib/research-gateway';
import type { Dataset, ResearchThread } from '@/types/research';
import { CashFlowComparison, EvidenceTable, ProfitabilityTable } from '@/components/research-evidence-table';
import { DetailDialog } from '@/components/ui/dialog';

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
    const usable = evidence.filter(item => !item.isDemo
      && (item.data.quality as { usable?: boolean } | undefined)?.usable !== false);
    const income = usable.find(item => item.toolName === 'get_financial_summary');
    const cashFlow = usable.find(item => item.toolName === 'get_fuyao_cash_flow' || item.toolName === 'get_cash_flow');
    const financeFirst = ['profitability', 'comprehensive'].includes(thread.researchScope?.type ?? '');
    const findings = report?.findings ?? [];
    const hasUsableEvidence = (finding: (typeof findings)[number]) =>
      finding.evidenceIds.length > 0 && finding.evidenceIds.every(id => usable.some(item => item.id === id));
    const mainFinding = findings.find(finding => ['现金流对照', '经营现金流与归母净利润对照'].includes(finding.task) && hasUsableEvidence(finding))
      ?? (financeFirst ? findings.find(finding => finding.evidenceIds.includes(income?.id ?? '') && hasUsableEvidence(finding)) : undefined)
      ?? findings.find(hasUsableEvidence);
    const mainReason = report?.comparisons?.length ? findings.find(finding => finding.task === '经营活动产生的现金流量净额变动原因') : undefined;
    const details = findings.filter(finding => finding !== mainFinding && finding !== mainReason);
    return <section className="card report answer-report">
      <div className="card-heading">
        <h2><FileText size={17} />研究结果</h2>
        {report && (annualGaps || !coverage) && <span className="report-version">有待核实的问题</span>}
      </div>
      {!report ? <div className="report-empty"><BookOpen size={24} />
        <p>{thread.status === 'running' ? '正在执行已批准的研究计划…' : '完成审批和执行后生成报告。'}</p>
      </div> : <>
        <div className="report-intro">
          <h3>结论摘要</h3>
          {report.period ? <p className="answer-period">实际取用 · {report.period}</p>
            : report.requestedPeriod ? <p className="answer-period">拟查 · {report.requestedPeriod} · 暂无可用结果</p>
            : income && <p className="answer-period">财务数据截至 {income.period}</p>}
          {mainFinding && <div className="answer-lead">
            <FindingContent finding={mainFinding} evidence={evidenceById} />
            {mainReason && mainReason !== mainFinding && <div className="mt-3 border-t pt-2">
              <FindingContent finding={mainReason} evidence={evidenceById} />
            </div>}
          </div>}
          {!mainFinding && <p>{report.executiveSummary}</p>}
          {Boolean(report.comparisons?.length) && <PeriodComparison rows={report.comparisons ?? []} />}
          {income && cashFlow && <CashFlowComparison income={income} cashFlow={cashFlow} onEvidence={onEvidence} />}
        </div>
        <div className="report-body">
          <div>
            {details.length > 0 && <h4>详细发现</h4>}
            {income && <details className="answer-disclosure"><summary>查看年度盈利趋势</summary>
              <ProfitabilityTable item={income} onOpen={() => onEvidence(income.id)} /></details>}
            <div className="answer-findings">
              {details.map((finding, index) => <article key={`${finding.task}-${index}`}>
                <h5 className="font-semibold">{finding.task}</h5>
                <FindingContent finding={finding} evidence={evidenceById} />
              </article>)}
            </div>
          </div>
          <details className="answer-disclosure answer-limitations">
            <summary>数据范围与限制{limitations.length > 0 ? `（${limitations.length}）` : ''}</summary>
            <p className="mt-2">{report.executiveSummary}</p><p>{report.dataNotice}</p>
            <p className="mb-2">证据检查：{report.qualityStatus === 'FAIL' ? '有证据未通过检查' : report.qualityStatus === 'WARN' ? '有核验提示，详见各条证据' : report.qualityStatus === 'PASS' ? '基础检查通过' : '未完成统一检查'}</p>
            {limitations.length ? limitations.map(({ message, ids }) => <div key={message} className="mb-2">
              <p>{message}</p>
              {ids.map(id => evidenceById.has(id) && <button key={id} type="button" className="citation mr-1 text-xs"
                onClick={() => onEvidence(id)} aria-label={`查看证据 ${id}`}>{id}</button>)}
            </div>) : <p>暂无额外缺失信息。</p>}
          </details>
          {review}
        </div>
        {evidence.length > 0 && <details className="evidence-footer answer-disclosure">
          <summary>数据来源与证据（{evidence.length}）</summary>
          {evidence.map(item => <FindingEvidence key={item.id} item={item} onOpen={() => onEvidence(item.id)} showExcerpts={!report.annualAnswers} />)}
        </details>}
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

const kindLabel = { disclosed: '公司披露', computed: '系统计算', observed: '接口或资料记录', gap: '证据缺口', interpretation: '分析说明' };
const displayNumber = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });

function PageLink({ source, page }: { source: unknown; page: number }) {
  const url = sourceUrl(source);
  if (!url || !Number.isInteger(page) || page <= 0) return <span>PDF 第 {page} 页</span>;
  const link = new URL(url);
  link.hash = `page=${page}`;
  return <a className="citation" href={link.href} target="_blank" rel="noreferrer">PDF 第 {page} 页</a>;
}

function PeriodComparison({ rows }: { rows: FilingComparison[] }) {
  return <section className="answer-metrics" aria-label="财报指标对照">
    <h4>财报指标对照</h4>
    <div className="overflow-x-auto"><table>
      <thead><tr>{['指标', '本期（亿元）', '对照期（亿元）', '变动', '原文'].map(label =>
        <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.label}>
        <th scope="row">{row.label}<small className="block font-normal text-slate-600">{row.basis}</small></th>
        <td>{displayNumber(row.current / 1e8)}<small className="block text-slate-600">{row.period}</small></td>
        <td>{row.previous === null ? '未列示' : displayNumber(row.previous / 1e8)}
          <small className="block text-slate-600">{row.comparison_period}</small></td>
        <td>{row.change === null ? '—' : <>{row.change_basis} {row.change > 0 ? '+' : ''}{displayNumber(row.change)}%
          <small className="block text-slate-600">{kindLabel[row.change_kind]}</small></>}</td>
        <td><PageLink source={row.source} page={row.page} /></td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

export function FindingContent({ finding, evidence }: {
  finding: ResearchFinding; evidence: Map<string, ResearchEvidence>;
}) {
  const [open, setOpen] = useState(false);
  const sources = finding.evidenceIds.flatMap(id => evidence.get(id) ?? []);
  const refs = finding.excerpt_refs ?? [];
  const pages = new Map(finding.claims?.filter(claim => claim.page).map(claim =>
    [`${claim.evidence_id}-${claim.page}`, { source: claim.source, page: claim.page! }]));
  const excerpts = refs.flatMap(ref => {
    const item = evidence.get(ref.evidence_id);
    const rows = item?.data[ref.collection ?? 'records'] as Array<{ source?: string; page: number; text?: string }> | undefined;
    const row = rows?.[ref.record_index];
    if (!item || !row) return [];
    const source = row.source ?? item.data.source;
    if (sourceUrl(source)) pages.set(`${item.id}-${row.page}`, { source: sourceUrl(source), page: row.page });
    return [{ ...row, id: `${item.id}-${ref.record_index}` }];
  });
  return <>
    <p className="mt-1">{finding.kind && <strong className={finding.kind === 'gap' ? 'mr-2 text-sm text-amber-900' : 'mr-2 text-sm text-slate-600'}>{kindLabel[finding.kind]}</strong>}{finding.statement}</p>
    <div className="flex flex-wrap items-center gap-1">
      {(sources.length > 0 || Boolean(finding.claims?.length || finding.limitations?.length)) &&
        <button type="button" className="citation" onClick={() => setOpen(true)} aria-label={`查看依据 · ${finding.task}`}>查看依据</button>}
      {finding.evidenceIds.length > sources.length && <span className="text-sm text-amber-800">部分引用暂不可读取</span>}
      {[...pages].map(([key, value]) => <PageLink key={key} {...value} />)}
      {finding.source_links?.map(link => {
        const url = sourceUrl(link.url);
        return url && <a className="citation" key={url} href={url} target="_blank" rel="noreferrer">{link.label}</a>;
      })}
    </div>
    <DetailDialog open={open} onOpenChange={setOpen} title="结论依据" description={finding.task}>
    <div className="space-y-4 text-sm">
    {Boolean(finding.claims?.length) && <section>
      <h3 className="font-semibold">字段与计算</h3>
      <ul className="space-y-2 py-2">{finding.claims?.map((claim, index) => <li key={index}>
        <strong>{claim.basis}</strong> · {claim.period ?? '参见取数时间'}{claim.comparison_period && ` · 对照 ${claim.comparison_period}`}
        {claim.base_value != null && ['growth_percent', 'ratio_percent'].includes(claim.formula)
          ? <p>（{displayNumber(claim.raw_value)} ÷ {displayNumber(claim.base_value * (claim.base_multiplier ?? 1))}{claim.formula === 'growth_percent' ? ' − 1' : ''}）× 100 = {displayNumber(claim.value)}%</p>
          : <p>{displayNumber(claim.raw_value)} {claim.unit}</p>}
        <code className="break-all text-xs text-slate-600">{[claim.field, claim.base_field].filter(Boolean).join(' / ')}</code>
      </li>)}</ul>
    </section>}
    {excerpts.map(row => <blockquote key={row.id} className="rounded bg-slate-50 p-3">
      <strong>财报第 {row.page} 页</strong><p className="whitespace-pre-wrap">{row.text}</p>
    </blockquote>)}
    {sources.map(item => <details className="border-t pt-2" key={item.id}>
      <summary className="cursor-pointer font-medium">{item.title}</summary>
      <div className="mt-2"><EvidenceTable item={item} /></div>
    </details>)}
    {Boolean(finding.limitations?.length) && <section className="text-amber-900">
      <h3 className="font-semibold">核验提示</h3>
      <ul className="list-disc pl-5">{finding.limitations?.map(issue => <li key={issue}>{issue}</li>)}</ul>
    </section>}
    </div>
    </DetailDialog>
  </>;
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
