import type { ResearchThread, RunAction, TraceEvent } from '../types/research';

// Pure, explicit UI-demo transition boundary. Invalid transitions are no-ops.
export function transition(thread: ResearchThread, action: RunAction): ResearchThread {
  let next = { ...thread }; let title = ''; let detail = ''; let kind: TraceEvent['kind'] = 'info';
  const time = 'time' in action ? action.time : '本次会话';
  switch (action.type) {
    case 'START':
      if (!['idle', 'cancelled', 'completed'].includes(thread.status) || !action.goal.trim()) return thread;
      next = { ...next, goal: action.goal.trim(), status: 'running', step: 0, calls: 0, tokens: 0, latency: 0, checkpoint: null, approval: 'pending', recovered: false, events: [] };
      title = '研究演示已启动'; detail = '本地状态机开始推进预设计划。'; break;
    case 'TICK':
      if (thread.status !== 'running') return thread;
      next.step += 1; next.calls += 2; next.tokens += 1240; next.latency = +(next.latency + 3.1).toFixed(1);
      if (next.step === 2 && next.approval === 'pending') { next.status = 'approval'; title = '扩展工具等待审批'; kind = 'warning'; }
      else if (next.step >= 5) { next.status = 'completed'; title = '演示报告已完成'; kind = 'success'; }
      else { title = next.step === 4 ? '上下文压缩完成（演示）' : `计划步骤 ${next.step} 已完成`; kind = 'success'; }
      detail = next.step === 4 ? '8,240 → 3,120 tokens；保留目标、事实摘要与证据编号。' : '仅推进前端演示，无外部调用。';
      next.checkpoint = { step: next.step, calls: next.calls, tokens: next.tokens, latency: next.latency, approval: next.approval }; break;
    case 'PAUSE': if (thread.status !== 'running') return thread; next.status = 'paused'; title = '用户暂停研究'; detail = '自动推进已停止。'; break;
    case 'RESUME': if (thread.status !== 'paused') return thread; next.status = 'running'; title = '用户恢复研究'; break;
    case 'CANCEL': if (!['running', 'paused', 'approval', 'failed'].includes(thread.status)) return thread; next.status = 'cancelled'; title = '研究已取消'; detail = '停止所有演示步骤；执行轨迹保留。'; kind = 'warning'; break;
    case 'APPROVE': case 'REJECT':
      if (thread.status !== 'approval') return thread;
      next.approval = action.type === 'APPROVE' ? 'approved' : 'rejected'; next.status = 'running';
      title = action.type === 'APPROVE' ? '用户批准扩展访问（演示）' : '用户拒绝扩展访问（演示）';
      detail = action.type === 'APPROVE' ? '允许继续展示行业对比步骤。' : '计划已调整：跳过行业对比，仅使用已有样本生成受限报告。';
      if (action.type === 'REJECT') next.step = 3;
      next.checkpoint = { step: next.step, calls: next.calls, tokens: next.tokens, latency: next.latency, approval: next.approval }; break;
    case 'FAIL': if (thread.status !== 'running') return thread; next.status = 'failed'; title = '模拟工具超时'; detail = 'market_snapshot 超过演示时限，执行停止。可从最近的本地检查点恢复。'; kind = 'error'; break;
    case 'RECOVER':
      if (thread.status !== 'failed') return thread;
      if (thread.checkpoint) Object.assign(next, thread.checkpoint);
      next.status = next.step === 2 && next.approval === 'pending' ? 'approval' : 'running'; next.recovered = true;
      title = '已从本地检查点恢复'; detail = '使用内存中的演示快照，切换到本地备用样本；没有后端恢复操作。'; kind = 'success'; break;
  }
  next.updated = time;
  next.events = [...next.events, { id: Number(next.events.at(-1)?.id ?? 0) + 1, time, title, detail, kind, tokens: action.type === 'TICK' ? 1240 : 0, latency: action.type === 'TICK' ? 3.1 : 0 }];
  return next;
}
