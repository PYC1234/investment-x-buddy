'use client';
import { useState } from 'react';
import { ChevronDown, CircleCheck, CircleDashed, CircleDot, LockKeyhole, Pause, Play, RotateCcw, ShieldCheck, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { steps as demoSteps } from '@/data/demo';
import type { AppMode } from '@/lib/research-gateway';
import type { ResearchThread } from '@/types/research';

type Action = 'APPROVE'|'REJECT'|'PAUSE'|'RESUME'|'CANCEL'|'FAIL'|'RECOVER'|'TICK'|'RETRY_FAILED';

type RevisionResponse = { message: string; error: boolean; planUnchanged?: boolean };
type Revise = (goal: string, excludedTools: string[], feedback?: string, fiscalYear?: number) => Promise<RevisionResponse | null>;

function plannedFiscalYear(thread: ResearchThread) {
  const periodic = thread.tasks?.find(task => task.toolName === 'read_official_periodic_report')?.arguments;
  if (periodic?.kind === 'annual' && typeof periodic.year === 'number') return periodic.year;
  const args = thread.tasks?.find(task => task.toolName === 'get_financial_summary')?.arguments;
  return args?.require_fiscal_year === true && typeof args.fiscal_year === 'number' ? args.fiscal_year : undefined;
}

function PlanRevision({ thread, onRevise, onAction }: { thread: ResearchThread; onRevise: Revise; onAction: (action: Action) => void }) {
  const [goal, setGoal] = useState(thread.goal);
  const [feedback, setFeedback] = useState('');
  const [fiscalYear, setFiscalYear] = useState<number | undefined>();
  const [excluded, setExcluded] = useState<string[]>([]);
  const [response, setResponse] = useState<RevisionResponse | null>(null);
  const tools = [...new Map((thread.tasks ?? []).map(task => [task.toolName, task.title])).entries()];
  const currentYear = plannedFiscalYear(thread);
  const latestClosedYear = Math.min(2030, new Date().getFullYear() - 1);
  const changedYear = fiscalYear !== undefined && fiscalYear !== currentYear;
  const changed = goal.trim() !== thread.goal || excluded.length > 0 || feedback.trim().length > 0 || changedYear;
  return <form className="card space-y-3 p-5" onSubmit={async event => {
    event.preventDefault();
    setResponse(null);
    setResponse(await onRevise(goal.trim(), excluded, feedback.trim(), changedYear ? fiscalYear : undefined));
  }}>
    <h3 className="font-semibold">确认 Plan v{thread.planVersion}</h3>
    <p className="text-sm text-slate-600">计划合适就批准执行。需要调整时，先提交修改意见，再核对新版计划。</p>
    <label className="block text-sm font-medium" htmlFor="research-plan-feedback">修改意见</label>
    <textarea id="research-plan-feedback" className="w-full rounded border p-2 text-sm" value={feedback}
      onChange={event => { setFeedback(event.target.value); setResponse(null); }} disabled={thread.loading} rows={3} maxLength={500}
      placeholder="例如：先别看股价，我想知道利润有没有现金流支撑。" />
    <details className="space-y-2">
      <summary className="cursor-pointer text-sm">调整财年、研究要求或工具</summary>
      <label className="flex items-center gap-2 text-sm" htmlFor="research-fiscal-year">锁定财年
        <select id="research-fiscal-year" className="rounded border p-2" disabled={thread.loading}
          value={fiscalYear ?? ''} onChange={event => setFiscalYear(event.target.value ? Number(event.target.value) : undefined)}>
          <option value="">沿用当前计划</option>
          {Array.from({ length: Math.max(0, latestClosedYear - 2019) },
            (_, index) => latestClosedYear - index).map(year => <option key={year} value={year}>{year} 财年</option>)}
        </select>
      </label>
      <p className="text-xs text-slate-600">选择财年后，将生成对应年度的财报研究计划。</p>
      <label className="block text-sm font-medium" htmlFor="revised-research-goal">研究要求</label>
      <textarea id="revised-research-goal" className="w-full rounded border p-2 text-sm" value={goal}
        onChange={event => setGoal(event.target.value)} disabled={thread.loading} rows={2} minLength={3} maxLength={1000} required />
    {tools.length > 1 && <fieldset className="space-y-1" disabled={thread.loading}>
      <legend className="mb-1 text-sm font-medium">取消不需要的工具</legend>
      {tools.map(([name, title]) => <label key={name} className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={excluded.includes(name)} onChange={event => {
          const checked = event.target.checked;
          setExcluded(current => checked ? [...current, name] : current.filter(tool => tool !== name));
        }} />
        {title}
      </label>)}
    </fieldset>}
    </details>
    {response && <div role={response.error ? 'alert' : 'status'} className={response.error ? 'text-sm text-red-700' : 'space-y-1 rounded bg-slate-50 p-3 text-sm'}>
      <p>{response.message}</p>
      {response.planUnchanged && <p>这次意见未应用。你可以修改后重试，或按当前 Plan v{thread.planVersion} 执行。</p>}
    </div>}
    <div className="flex flex-wrap gap-2">
      <Button type="submit" disabled={thread.loading || !changed || goal.trim().length < 3 || (goal.trim() === thread.goal && excluded.length === tools.length)}>{thread.loading ? '生成中…' : '生成新版计划'}</Button>
      <Button type="button" disabled={thread.loading || changed} onClick={() => onAction('APPROVE')}>批准并执行</Button>
      {response?.planUnchanged && changed && <Button type="button" variant="outline" disabled={thread.loading} onClick={() => {
        setGoal(thread.goal); setFeedback(''); setExcluded([]); setFiscalYear(undefined); setResponse(null);
        onAction('APPROVE');
      }}>放弃意见，批准 Plan v{thread.planVersion}</Button>}
      {changed && <Button type="button" variant="outline" disabled={thread.loading} onClick={() => {
        setGoal(thread.goal); setFeedback(''); setExcluded([]); setFiscalYear(undefined); setResponse(null);
      }}>清空修改</Button>}
      <Button type="button" variant="outline" disabled={thread.loading} onClick={() => onAction('REJECT')}>拒绝计划</Button>
    </div>
  </form>;
}

export function ResearchPlan({ thread, expanded, setExpanded, onAction, onRevise, mode }: { thread: ResearchThread; expanded: number | null; setExpanded: (n: number | null) => void; onAction: (action: Action) => void; onRevise: Revise; mode: AppMode }) {
  const versionKey = `${thread.remoteRunId}:${thread.planVersion}`;
  const revision = thread.researchScope?.revisionNote;
  const fiscalYear = plannedFiscalYear(thread);
  const periodicScope = thread.plannerMode === 'periodic_filing' ? thread.researchScope?.scope[0] : undefined;
  const taskTitles = new Map(thread.tasks?.map(task => [task.taskKey, task.title]));
  const plannedTools = new Set(thread.tasks?.map(task => task.toolName));
  const sources = [...new Set(thread.apiTools?.filter(tool => plannedTools.has(tool.name)).map(tool => ({
    'FUYAO / MARKET DATA': '扶摇数据接口', 'CNINFO PUBLIC FILINGS': '巨潮资讯公开财报',
    'IMPORTED PUBLIC SOURCES': '已导入公开资料', 'USER UPLOADED REPORT': '本次上传的年报',
    'FIXTURE / DEMO DATA': '演示数据',
  } as Record<string, string>)[tool.permission] ?? tool.permission).filter(Boolean))];
  const steps = mode === 'api'
    ? (thread.tasks ?? []).map(task => ({ title: task.title, tool: task.toolName, detail: [task.rationale, task.question ? `研究问题：${task.question}` : '', task.dependsOn?.length ? `先完成：${task.dependsOn.map(key => taskTitles.get(key) ?? key).join('、')}` : '', task.completionCriteria?.length ? `完成标准：${task.completionCriteria.join('；')}` : ''].filter(Boolean).join('；'), status: task.status, error: task.error, attempts: task.attempts }))
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
        {(periodicScope || thread.tasks?.some(task => task.toolName === 'get_financial_summary')) && <div><dt className="inline text-slate-500">财报期间：</dt><dd className="inline">{periodicScope ?? (fiscalYear ? `${fiscalYear} 财年，对照 ${fiscalYear - 1} 财年` : '最新可用年度，由数据接口返回结果确认')}</dd></div>}
        {!periodicScope && <div><dt className="inline text-slate-500">数据范围：</dt><dd className="inline">{thread.researchScope?.scope.length ? thread.researchScope.scope.join('；') : steps.map(step => step.title).join('；')}</dd></div>}
        <div><dt className="inline text-slate-500">工具来源：</dt><dd className="inline">{sources.length ? sources.join('、') : '来源以执行后的证据为准'}</dd></div>
      </dl>
      <div className="mt-3 rounded-md bg-amber-50 p-3 text-xs leading-6 text-amber-900"><strong>待核验与限制</strong><ul className="list-disc pl-4">{(thread.researchScope?.limitations.length ? thread.researchScope.limitations : ['标的存在与数据覆盖将在执行时验证。']).map(item => <li key={item}>{item}</li>)}</ul>{thread.status === 'approval' && <p>请核对标的、研究重点和工具。你可以先修改计划，再批准执行。</p>}</div>
    </section>}
    {revision && thread.status === 'approval' && <section className="card space-y-2 p-5" aria-label="本次计划修改">
      <h3 className="font-semibold">本次计划修改</h3>
      <p className="text-sm">{revision.understood}</p>
      {([['新增', revision.added], ['移除', revision.removed], ['保留', revision.kept]] as const).map(([label, items]) =>
        items.length > 0 && <p key={label} className="text-sm"><strong>{label}</strong> {items.join('、')}</p>)}
    </section>}
    <section className="card plan-card">
      <div className="card-heading"><h2>研究执行计划 <span>{steps.length} 步 · {mode === 'api' ? ({ fixture: '规则规划', deepseek: 'DeepSeek 规划', annual_update: '年报研究规划' }[thread.plannerMode ?? ''] ?? '后端规划') : '本地演示'}</span></h2><div className="run-actions">
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
    {thread.status === 'approval' && (mode === 'api'
      ? <PlanRevision key={versionKey} thread={thread} onRevise={onRevise} onAction={onAction} />
      : <section className="approval-card"><div className="approval-icon"><LockKeyhole /></div><div><h3>允许扩展行业对比样本？</h3><p>演示请求将增加一次本地工具步骤。</p><div className="permission-line"><ShieldCheck /> peer_comparison · read:demo-peers</div></div><div className="approval-actions"><Button onClick={() => onAction('APPROVE')}>批准演示步骤</Button><Button variant="outline" onClick={() => onAction('REJECT')}>拒绝计划</Button></div></section>)}
    {['failed','partial'].includes(thread.status) && <section className="failure-card"><div><strong>{thread.status === 'partial' ? '研究部分完成' : '执行已停止'}</strong><p>{mode === 'api' ? retryFailed ? `有 ${failedTasks.length} 项失败。每次只重试失败项一次，沿用原审批与参数，保留成功证据；调用预算不重置。` : '请在 Trace 和报告中查看停止原因。恢复仅继续未完成任务；规划失败请新建研究。' : '模拟工具超时。最近检查点仍可用于恢复。'}</p>{retryFailed && <ul className="mt-2 space-y-1 text-xs">{failedTasks.map(task => <li key={task.id}>{task.title}：{task.error ?? '执行失败'} · 累计 {task.attempts} 次尝试</li>)}</ul>}</div><Button disabled={thread.loading || (mode === 'api' && thread.approval !== 'approved')} onClick={() => onAction(mode === 'api' ? retryFailed ? 'RETRY_FAILED' : 'RESUME' : 'RECOVER')}><RotateCcw />{retryFailed ? '重试失败任务' : '从检查点恢复'}</Button></section>}
  </div>;
}
