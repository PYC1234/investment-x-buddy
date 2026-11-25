'use client';
import { ArrowUpRight, Sparkles, CornerDownLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { researchApi } from '@/lib/research-gateway';
import type { AnnualScope, ResearchThread } from '@/types/research';
import type { ReactNode } from 'react';
export function buildExampleGoal(thread: Pick<ResearchThread, 'company' | 'code'>, focus: string) {
 const code = thread.code.trim().toUpperCase();
 const company = thread.company.trim();
 const hasName = company && !['研究工作台', '自定义研究', '尚未指定证券'].includes(company);
 const target = /^\d{6}\.(SH|SZ)$/.test(code)
  ? (hasName && company !== code ? `${company}（${code}）` : code)
  : '贵州茅台（600519.SH）';
 if (focus === "年度财报更新") {
  const year = new Date().getFullYear() - 1;
  return `请对${target}做 ${year} 年财报更新，核对盈利变化与年报原文。`;
 }
 return `请对${target}进行${focus}，列出证据和不确定性。`;
}
export function ResearchInput({ thread, goal, setGoal, onStart, onAnnualStart, documentMode=false, busy=false, children }: { thread: ResearchThread; goal: string; setGoal: (value: string) => void; onStart: () => void; onAnnualStart?: (scope: AnnualScope) => Promise<void>; documentMode?:boolean; busy?:boolean; children?:ReactNode }) {
 const canStart = !busy && (documentMode || (['idle', 'cancelled', 'completed', 'partial', 'failed', 'rejected'].includes(thread.status) && !thread.loading));
 return <section className="input-card"><div className="flex items-center gap-2 text-xs font-semibold text-slate-700"><Sparkles size={16} className="text-blue-700" />你的下一个研究问题是什么？<span className="ml-auto text-[10px] font-normal text-slate-400">{documentMode?'当前来源：已附资料':'当前来源：联网研究'}</span></div><textarea aria-label="研究目标" maxLength={1000} disabled={!canStart} placeholder={documentMode?'例如：比较附件中的管理费率，说明差异并引用原文；也可以继续追问…':'输入研究问题，或在下方添加资料后围绕文件提问；研究 A 股请提供六位证券代码…'} value={goal} onChange={e => setGoal(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canStart && goal.trim()) onStart(); }} />{children}{!documentMode && onAnnualStart && <AnnualResearchForm key={thread.id} thread={thread} disabled={!canStart} onStart={onAnnualStart} />}<div className="input-actions"><div className="example-goals">{(documentMode?['总结资料要点并引用来源','比较费用，说明数据缺失']:['盈利能力分析', '估值与风险']).map(s => <button key={s} title={documentMode?s:buildExampleGoal(thread, s)} disabled={!canStart} onClick={() => setGoal(documentMode?s:buildExampleGoal(thread, s))}>{s}<ArrowUpRight size={11} /></button>)}</div><Button onClick={onStart} disabled={!canStart || !goal.trim()}><span>{busy?'正在分析…':documentMode?'发送资料问题':'Start Research'}</span><CornerDownLeft size={13} /></Button></div></section>;
}

function AnnualResearchForm({ thread, disabled, onStart }: { thread: ResearchThread; disabled: boolean; onStart: (scope: AnnualScope) => Promise<void> }) {
  const [symbol, setSymbol] = useState(thread.code.trim().toUpperCase());
  const latest = Math.min(2030, new Date().getFullYear() - 1);
  const [year, setYear] = useState(latest);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const scope = { symbol: symbol.trim().toUpperCase(), fiscal_year: year };
  const valid = /^\d{6}\.(SH|SZ)$/.test(scope.symbol);
  return <details className="mt-2 rounded border p-3 text-sm">
    <summary className="cursor-pointer font-semibold">年度财报更新</summary>
    <form className="mt-2 grid gap-2" onSubmit={async event => {
      event.preventDefault();
      if (!valid || disabled || busy) return;
      setBusy(true);
      try { await onStart(scope); } finally { setBusy(false); }
    }}>
      <div className="flex flex-wrap gap-3">
        <label>公司代码 <input className="rounded border px-2 py-1" placeholder="600519.SH" value={symbol}
          onChange={event => { setSymbol(event.target.value); setMessage(''); }} maxLength={9} disabled={disabled || busy} required /></label>
        <label>财年 <select className="rounded border px-2 py-1" value={year} disabled={disabled || busy}
          onChange={event => { setYear(Number(event.target.value)); setMessage(''); }}>
          {Array.from({ length: latest - 2019 }, (_, i) => latest - i).map(value => <option key={value}>{value}</option>)}
        </select></label>
      </div>
      <p>研究范围：{valid ? scope.symbol : '待选公司'} · {year} 财年及上年对照</p>
      {message && <p role="status">{message}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" disabled={!valid || disabled || busy} onClick={async () => {
          setBusy(true);
          try {
            const result = await researchApi.annualAvailability(scope);
            setMessage(result.ok ? (result.data.filing_available ? '已识别该财年的年报资料。' : '暂无已导入年报，可在生成报告后上传 PDF 补查。') : result.error);
          } finally { setBusy(false); }
        }}>检查资料</Button>
        <Button type="submit" disabled={!valid || disabled || busy}>生成研究计划</Button>
      </div>
    </form>
  </details>;
}
