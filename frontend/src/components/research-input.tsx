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
 const examples = documentMode ? ['总结资料要点并引用来源', '比较费用，说明数据缺失']
   : thread.code ? [buildExampleGoal(thread, '盈利能力分析'), buildExampleGoal(thread, '估值与风险')]
   : ['贵州茅台 2025 年经营现金流为什么下降？请引用年报原文。',
      '宁德时代最近的股价走势怎样？结合市盈率和市净率，看看估值风险。'];
 return <section className="input-card">
   <div className="flex items-center gap-2 text-xs font-semibold text-slate-700"><Sparkles size={16} className="text-blue-700" />
     <label htmlFor="research-question">研究问题</label>
     <span className="ml-auto text-[11px] font-normal text-slate-600">{documentMode ? '资料问答' : 'A 股研究'}</span>
   </div>
   <textarea id="research-question" aria-label="研究目标" maxLength={1000} disabled={!canStart}
     placeholder={documentMode ? '输入关于附件的问题…' : '输入公司名称和你想了解的问题…'}
     value={goal} onChange={event => setGoal(event.target.value)} onKeyDown={event => {
       if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && canStart && goal.trim()) onStart();
     }} />
   {children}
   <div className="input-actions">
     <div className="example-goals">{examples.map(example => <button type="button" key={example} disabled={!canStart}
       onClick={() => setGoal(example)}>{example}<ArrowUpRight size={11} /></button>)}</div>
     <Button type="button" onClick={onStart} className="shrink-0" disabled={!canStart || !goal.trim()}>
       {busy ? '正在分析…' : documentMode ? '发送资料问题' : '生成研究计划'}<CornerDownLeft size={13} />
     </Button>
   </div>
 </section>;
}
