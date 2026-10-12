'use client';
import { ChevronDown, CircleCheck, CircleDashed, CircleDot, LockKeyhole, Pause, Play, RotateCcw, ShieldCheck, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { steps as demoSteps } from '@/data/demo';
import type { AppMode } from '@/lib/research-gateway';
import type { ResearchThread } from '@/types/research';

type Action = 'APPROVE'|'REJECT'|'PAUSE'|'RESUME'|'CANCEL'|'FAIL'|'RECOVER'|'TICK'|'RETRY_FAILED';

export function ResearchPlan({ thread, expanded, setExpanded, onAction, mode }: { thread: ResearchThread; expanded: number | null; setExpanded: (n: number | null) => void; onAction: (action: Action) => void; mode: AppMode }) {
  const steps = mode === 'api'
    ? (thread.tasks ?? []).map(task => ({ title: task.title, tool: task.toolName, detail: task.rationale, status: task.status, error: task.error, attempts: task.attempts }))
    : demoSteps.map((step, index) => ({ ...step, status: index < thread.step ? 'COMPLETED' : 'PENDING', error: null, attempts: 0 }));
  const failedTasks = (thread.tasks ?? []).filter(task => task.status === 'FAILED');
  const retryFailed = mode === 'api' && failedTasks.length > 0;
  const total = Math.max(steps.length, 1);
  return <div className="plan-stack">
    {mode === 'api' && steps.length > 0 && <section className="card p-5" aria-label="本次研究确认">
      <h2 className="mb-3 font-semibold">本次研究确认</h2>
      <dl className="space-y-2 text-sm">
        <div><dt className="inline text-slate-500">研究标的：</dt><dd className="inline">{thread.company} · {thread.code} · 沪深 A 股</dd></div>
        <div><dt className="inline text-slate-500">研究重点：</dt><dd className="inline">{({profitability: '盈利能力', valuation: '估值分析', risk: '风险线索', comprehensive: '综合研究'} as Record<string, string>)[thread.researchScope?.type ?? 'comprehensive'] ?? '综合研究'}</dd></div>
        <div><dt className="inline text-slate-500">数据范围：</dt><dd className="inline">{thread.researchScope?.scope.length ? thread.researchScope.scope.join('；') : steps.map(step => step.title).join('；')}</dd></div>
        <div><dt className="inline text-slate-500">工具来源：</dt><dd className="inline">{thread.apiTools?.some(tool => tool.permission.includes('FUYAO')) ? '扶摇真实接口；行情为最近可用数据' : '来源以注册工具及执行后证据为准'}</dd></div>
      </dl>
      <div className="mt-3 rounded-md bg-amber-50 p-3 text-xs leading-6 text-amber-900"><strong>尚未覆盖</strong><ul className="list-disc pl-4">{(thread.researchScope?.limitations.length ? thread.researchScope.limitations : ['完整财报、历史估值和独立风险核验尚未覆盖。']).map(item => <li key={item}>{item}</li>)}</ul><p>请核对标的和范围，再批准下方工具。标的存在与数据覆盖将在执行时验证；如需修改，请拒绝计划后新建研究。</p></div>
    </section>}
    <section className="card plan-card">
      <div className="card-heading"><h2>研究执行计划 <span>{steps.length} steps · {mode === 'api' ? `${thread.plannerMode ?? 'backend'} planner` : 'UI state machine'}</span></h2><div className="run-actions">
        {mode === 'demo' && thread.status === 'running' && <Button variant="outline" size="sm" onClick={() => onAction('PAUSE')}><Pause />暂停</Button>}
        {mode === 'demo' && thread.status === 'paused' && <Button variant="outline" size="sm" onClick={() => onAction('RESUME')}><Play />恢复</Button>}
        {mode === 'api' && ['failed','partial'].includes(thread.status) && <Button variant="outline" size="sm" disabled={thread.loading || thread.approval !== 'approved'} onClick={() => onAction(retryFailed ? 'RETRY_FAILED' : 'RESUME')}><RotateCcw />{retryFailed ? '重试失败任务' : '恢复'}</Button>}
        {['running','paused','approval','failed','partial'].includes(thread.status) && <Button variant="destructive" size="sm" disabled={thread.loading} onClick={() => onAction('CANCEL')}><Square />停止</Button>}
      </div></div>
      <div className="progress-track"><span style={{ width: `${Math.max(4, thread.step / total * 100)}%` }} /></div>
      <div className="steps">{steps.length ? steps.map((step, index) => {
        const done = step.status === 'COMPLETED';
        const current = ['RUNNING', 'PENDING'].includes(step.status) && !['completed','cancelled','rejected'].includes(thread.status);
        return <div className={`step ${done ? 'done' : ''} ${current ? 'current' : ''}`} key={`${step.tool}-${index}`}><button aria-expanded={expanded === index} onClick={() => setExpanded(expanded === index ? null : index)}><span className="step-icon">{done ? <CircleCheck /> : current ? <CircleDot /> : <CircleDashed />}</span><span><strong>{index + 1}. {step.title}</strong><small>{step.tool} · {step.status}{step.attempts ? ` · ${step.attempts} attempt(s)` : ''}</small></span><ChevronDown className={expanded === index ? 'rotate-180' : ''} /></button>{expanded === index && <div className="step-detail">{step.detail}<span>{step.error ? `错误：${step.error}` : mode === 'api' ? '权限：审批工具范围内只读执行' : '权限：本地演示'}</span></div>}</div>;
      }) : <div className="empty-state">尚未生成后端计划。</div>}</div>
      {mode === 'demo' && thread.status === 'running' && <div className="plan-footer"><Button onClick={() => onAction('TICK')}>推进下一演示步骤 <Play /></Button><Button variant="outline" onClick={() => onAction('FAIL')}>模拟工具失败</Button></div>}
    </section>
    {thread.status === 'approval' && <section className="approval-card"><div className="approval-icon"><LockKeyhole /></div><div><span className="eyebrow">HUMAN APPROVAL REQUIRED</span><h3>{mode === 'api' ? `批准 Plan v${thread.planVersion} 的工具范围？` : '允许扩展行业对比样本？'}</h3><p>{mode === 'api' ? '批准后后端才会执行上方注册工具。批准请求绑定当前计划版本和完整工具白名单。' : '演示请求将增加一次本地工具步骤，不连接金融 API。'}</p><div className="permission-line"><ShieldCheck /> {mode === 'api' ? [...new Set((thread.tasks ?? []).map(task => task.toolName))].join(' · ') : 'peer_comparison · read:demo-peers'}</div></div><div className="approval-actions"><Button disabled={thread.loading} onClick={() => onAction('APPROVE')}>{thread.loading ? '执行中…' : mode === 'api' ? '批准并执行' : '批准演示步骤'}</Button><Button variant="outline" disabled={thread.loading} onClick={() => onAction('REJECT')}>拒绝计划</Button></div></section>}
    {['failed','partial'].includes(thread.status) && <section className="failure-card"><div><strong>{thread.status === 'partial' ? '研究部分完成' : '执行已停止'}</strong><p>{mode === 'api' ? retryFailed ? `有 ${failedTasks.length} 项失败。每次只重试失败项一次，沿用原审批与参数，保留成功证据；调用预算不重置。` : '请在 Trace 和报告中查看停止原因。恢复仅继续未完成任务；规划失败请新建研究。' : '模拟工具超时。最近检查点仍可用于恢复。'}</p>{retryFailed && <ul className="mt-2 space-y-1 text-xs">{failedTasks.map(task => <li key={task.id}>{task.title}：{task.error ?? '执行失败'} · 累计 {task.attempts} 次尝试</li>)}</ul>}</div><Button disabled={thread.loading || (mode === 'api' && thread.approval !== 'approved')} onClick={() => onAction(mode === 'api' ? retryFailed ? 'RETRY_FAILED' : 'RESUME' : 'RECOVER')}><RotateCcw />{retryFailed ? '重试失败任务' : '从检查点恢复'}</Button></section>}
  </div>;
}
