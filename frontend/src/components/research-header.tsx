import { Menu, FlaskConical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { statusLabels } from '@/data/demo';
import type { ResearchThread } from '@/types/research';
import { configuredMode, type AppMode } from '@/lib/research-gateway';
export function ResearchHeader({ thread, onMenu, mode = configuredMode }: {
  thread: ResearchThread; onMenu: () => void; mode?: AppMode;
}) {
  const demoEvidence = mode === 'demo' || thread.apiDataset?.isDemo === true;
  return <header className="research-header">
    <div className="research-heading">
      <Button className="mobile-only" size="icon" variant="ghost" onClick={onMenu} aria-label="打开研究侧栏"><Menu /></Button>
      <div>
        {thread.code && <div className="stock-meta"><strong>{thread.company}</strong><span className="ticker">{thread.code}</span>{thread.sector && <span>{thread.sector}</span>}</div>}
        <h1>{thread.title}</h1>
        {demoEvidence && <span className="demo-evidence-label"><FlaskConical size={14} />DEMO DATA · 演示数据</span>}
      </div>
    </div>
    {thread.status !== 'idle' && <div className="header-state">
      <span className={`status-badge ${thread.status}`}><span className={`dot ${thread.status}`} />{statusLabels[thread.status]}</span>
    </div>}
  </header>;
}
