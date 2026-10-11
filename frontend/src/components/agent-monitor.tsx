'use client';
import { useState } from 'react';
import { Activity, BrainCircuit, Check, ChevronDown, CircleGauge, Clock3, Coins, DatabaseBackup, HardDriveDownload, ListTree, MemoryStick, RotateCcw, Shield, Wrench } from 'lucide-react';
import { toolsRegistry } from '@/data/demo';
import type { AppMode } from '@/lib/research-gateway';
import type { ResearchThread } from '@/types/research';

export function AgentMonitor({ thread, mode, apiError, onOpenPreferences, onSwitchDemo }: { thread: ResearchThread; mode: AppMode; apiError: string | null; onOpenPreferences: () => void; onSwitchDemo: () => void }) {
  const [open, setOpen] = useState('tools');
  const toggle = (id: string) => setOpen(open === id ? '' : id);
  const tools = mode === 'api' ? thread.apiTools ?? [] : toolsRegistry;
  const cost = mode === 'api' ? (thread.costUsd == null ? thread.costStatus ?? 'NOT_CONFIGURED' : `$${thread.costUsd.toFixed(6)}`) : `¥${(thread.tokens / 100000 * 1.8).toFixed(3)}`;
  const stateText = thread.loading ? '请求处理中' : thread.status === 'running' ? '正在执行计划' : thread.status === 'approval' ? '等待人工审批' : ['failed','partial'].includes(thread.status) ? '需要检查或恢复' : 'Agent 已就绪';
  return <aside className="monitor">
    <div className="monitor-head"><div><span className={`pulse ${thread.status}`} /><div><strong>Agent Monitor</strong><small>{mode === 'demo' ? 'LOCAL UI DEMO' : 'FASTAPI MODE'}</small></div></div><CircleGauge size={20} /></div>
    {apiError && <div className="api-error"><strong>真实 API 请求失败，未切换为成功演示。</strong><br/><span>{apiError}</span><button className="mode-switch" onClick={onSwitchDemo}>主动切换 Demo Mode</button></div>}
    <section className="agent-state"><div className="state-top"><span className="agent-orb"><BrainCircuit /></span><div><small>ORCHESTRATOR</small><strong>{stateText}</strong></div><span className={`state-pill ${thread.status}`}>{thread.apiStatus ?? thread.status.toUpperCase()}</span></div><div className="role-grid"><div><span>Planner</span><strong><Check />{thread.plannerMode ?? 'Ready'}</strong></div><div><span>Executor</span><strong>{thread.loading || thread.status === 'running' ? <><Activity />Active</> : 'Standby'}</strong></div></div></section>
    <div className="telemetry"><div><Wrench/><span>Tool calls<strong>{thread.calls}</strong></span></div><div><MemoryStick/><span>Token usage<strong>{thread.tokens.toLocaleString()}</strong></span></div><div><Coins/><span>Est. cost<strong>{cost}</strong></span></div><div><Clock3/><span>Latency<strong>{thread.latency.toFixed(3)}s</strong></span></div></div>
    <div className="monitor-section"><button onClick={() => toggle('tools')}><span><ListTree />Tool Registry</span><ChevronDown className={open === 'tools' ? 'rotate-180' : ''}/></button>{open === 'tools' && <div className="tool-list">{tools.map(tool => <div key={tool.name}><span className="tool-icon">{tool.name.slice(0,2).toUpperCase()}</span><span><strong>{tool.name}</strong><small>{tool.permission}</small></span></div>)}</div>}</div>
    <div className="monitor-section"><button onClick={() => toggle('context')}><span><HardDriveDownload />Context & Memory</span><ChevronDown className={open === 'context' ? 'rotate-180' : ''}/></button>{open === 'context' && <div className="monitor-detail"><div><span>上下文压缩</span><strong>{thread.checkpoint?.beforeChars ? `${thread.checkpoint.beforeChars} → ${thread.checkpoint.afterChars}` : mode === 'demo' && thread.step >= 4 ? '8,240 → 3,120' : '尚未触发'}</strong></div><div><span>长期记忆</span><button onClick={onOpenPreferences}>查看研究偏好</button></div><p>{mode === 'api' ? `SQLite Memory · ${Object.keys(thread.memory ?? {}).length} record(s)` : 'Demo Mode 仅保存在浏览器会话内。'}</p></div>}</div>
    <div className="monitor-section"><button onClick={() => toggle('checkpoint')}><span><DatabaseBackup />Checkpoint & Recovery</span><ChevronDown className={open === 'checkpoint' ? 'rotate-180' : ''}/></button>{open === 'checkpoint' && <div className="monitor-detail">{thread.checkpoint ? <><div><span>最近检查点</span><strong>{thread.checkpoint.sequence ? `#${thread.checkpoint.sequence}` : `Step ${thread.checkpoint.step}`}</strong></div><div><span>恢复状态</span><strong>{thread.recovered ? <><RotateCcw size={12}/> 已恢复</> : '可用'}</strong></div></> : <p>尚未生成检查点。</p>}</div>}</div>
    <div className="monitor-section"><button onClick={() => toggle('rules')}><span><Shield />Stop Rules</span><ChevronDown className={open === 'rules' ? 'rotate-180' : ''}/></button>{open === 'rules' && <div className="monitor-detail"><p>{mode === 'api' ? '后端限制工具次数、执行轮数、重试和总时限；错误进入 PARTIAL 报告。' : '审批超时即暂停 · 单步骤 15s · 用户取消立即停止'}</p></div>}</div>
    <footer className="monitor-foot"><DatabaseBackup />{mode === 'demo' ? '未连接真实 Agent · Memory-only' : `Run ${thread.remoteRunId?.slice(0, 8) ?? 'not created'} · SQLite`}</footer>
  </aside>;
}
