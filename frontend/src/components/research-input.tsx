'use client';
import { ArrowUpRight, Sparkles, CornerDownLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ResearchThread } from '@/types/research';
export function ResearchInput({ thread, goal, setGoal, onStart }: { thread: ResearchThread; goal: string; setGoal: (value: string) => void; onStart: () => void }) {
 const canStart = ['idle', 'cancelled', 'completed', 'partial', 'failed', 'rejected'].includes(thread.status) && !thread.loading;
 return <section className="input-card"><div className="flex items-center gap-2 text-xs font-semibold text-slate-700"><Sparkles size={16} className="text-blue-700" />你的下一个研究问题是什么？<span className="ml-auto text-[10px] font-normal text-slate-400">RESEARCH GOAL</span></div><textarea aria-label="研究目标" maxLength={1000} disabled={!canStart} placeholder="例如：分析宁德时代（300750.SZ）的盈利与估值；其他沪深 A 股请填写六位代码…" value={goal} onChange={e => setGoal(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canStart && goal.trim()) onStart(); }} /><div className="input-actions"><div className="example-goals">{['盈利能力分析', '估值与风险'].map(s => <button key={s} disabled={!canStart} onClick={() => setGoal(`请对${thread.company === '自定义研究' ? '贵州茅台' : thread.company}进行${s}，列出证据和不确定性。`)}>{s}<ArrowUpRight size={11} /></button>)}</div><Button onClick={onStart} disabled={!canStart || !goal.trim()}><span>Start Research</span><CornerDownLeft size={13} /></Button></div></section>;
}
