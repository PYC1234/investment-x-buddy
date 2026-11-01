'use client';
import { ArrowUpRight, Sparkles, CornerDownLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ResearchThread } from '@/types/research';
import type { ReactNode } from 'react';
export function buildExampleGoal(thread: Pick<ResearchThread, 'company' | 'code'>, focus: string) {
 const code = thread.code.trim().toUpperCase();
 const company = thread.company.trim();
 const hasName = company && !['研究工作台', '自定义研究', '尚未指定证券'].includes(company);
 const target = /^\d{6}\.(SH|SZ)$/.test(code)
  ? (hasName && company !== code ? `${company}（${code}）` : code)
  : '贵州茅台（600519.SH）';
 return `请对${target}进行${focus}，列出证据和不确定性。`;
}
export function ResearchInput({ thread, goal, setGoal, onStart, documentMode=false, busy=false, children }: { thread: ResearchThread; goal: string; setGoal: (value: string) => void; onStart: () => void; documentMode?:boolean; busy?:boolean; children?:ReactNode }) {
 const canStart = !busy && (documentMode || (['idle', 'cancelled', 'completed', 'partial', 'failed', 'rejected'].includes(thread.status) && !thread.loading));
 return <section className="input-card"><div className="flex items-center gap-2 text-xs font-semibold text-slate-700"><Sparkles size={16} className="text-blue-700" />你的下一个研究问题是什么？<span className="ml-auto text-[10px] font-normal text-slate-400">{documentMode?'当前来源：已附资料':'当前来源：联网研究'}</span></div><textarea aria-label="研究目标" maxLength={1000} disabled={!canStart} placeholder={documentMode?'例如：比较附件中的管理费率，说明差异并引用原文；也可以继续追问…':'输入研究问题，或在下方添加资料后围绕文件提问；研究 A 股请提供六位证券代码…'} value={goal} onChange={e => setGoal(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canStart && goal.trim()) onStart(); }} />{children}<div className="input-actions"><div className="example-goals">{(documentMode?['总结资料要点并引用来源','比较费用，说明数据缺失']:['盈利能力分析', '估值与风险']).map(s => <button key={s} title={documentMode?s:buildExampleGoal(thread, s)} disabled={!canStart} onClick={() => setGoal(documentMode?s:buildExampleGoal(thread, s))}>{s}<ArrowUpRight size={11} /></button>)}</div><Button onClick={onStart} disabled={!canStart || !goal.trim()}><span>{busy?'正在分析…':documentMode?'发送资料问题':'Start Research'}</span><CornerDownLeft size={13} /></Button></div></section>;
}
