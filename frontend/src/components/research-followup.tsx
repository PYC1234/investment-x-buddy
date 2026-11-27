'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FindingContent } from '@/components/research-report';
import { FollowupResearch } from '@/components/followup-research';
import { researchApi } from '@/lib/research-gateway';
import type { FollowupAnswer, ResearchThread } from '@/types/research';

interface Turn {
  question: string;
  previousQuestion?: string;
  history?: string[];
  contextRunId: string;
  contextRunIds?: string[];
  answer: FollowupAnswer;
  supplementId?: string;
}

function restoreTurns(key: string): Turn[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) ?? '[]');
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export function ResearchFollowup({ thread, visible }: { thread: ResearchThread; visible: boolean }) {
  const rootRunId = thread.remoteRunId ?? '';
  const storageKey = `investment-x-buddy.conversation:${rootRunId}`;
  const [turns, setTurns] = useState(() => restoreTurns(storageKey));
  const [research, setResearch] = useState<Record<string, ResearchThread>>({});
  const [question, setQuestion] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const tail = useRef<HTMLDivElement>(null);
  const scrollOnAnswer = useRef(false);
  const last = turns.at(-1);
  const completedRunIds = turns.flatMap(({ supplementId }) => supplementId && research[supplementId]?.apiReport
    && ['COMPLETE', 'PARTIAL'].includes(research[supplementId]?.apiStatus ?? '') ? [supplementId] : []);
  const contextRunId = completedRunIds.at(-1) ?? rootRunId;
  const evidence = new Map([...(thread.apiEvidence ?? []), ...Object.values(research).flatMap(run => run.apiEvidence ?? [])]
    .map(item => [item.id, item]));

  useEffect(() => {
    try { sessionStorage.setItem(storageKey, JSON.stringify(turns)); } catch { /* The current conversation remains in memory. */ }
  }, [storageKey, turns]);

  useEffect(() => {
    if (visible && scrollOnAnswer.current && tail.current) {
      scrollOnAnswer.current = false;
      tail.current.scrollIntoView({ block: 'end' });
    }
  }, [visible, last, pendingQuestion]);

  const rememberResearch = useCallback((run: ResearchThread) => {
    if (run.remoteRunId) setResearch(current => ({ ...current, [run.remoteRunId!]: run }));
  }, []);

  async function send(supplementIndex?: number) {
    const turn = supplementIndex === undefined ? undefined : turns[supplementIndex];
    const next = turn?.question ?? question.trim();
    const runId = turn?.contextRunId ?? contextRunId;
    const history = turn ? turn.history ?? (turn.previousQuestion ? [turn.previousQuestion] : [])
      : turns.slice(-6).map(entry => entry.question);
    const contextRunIds = turn ? turn.contextRunIds ?? []
      : [...new Set([rootRunId, ...completedRunIds.slice(-5)])].filter(id => id && id !== runId);
    if (!runId || busy || next.length < 2 || turn?.supplementId) return;
    setBusy(true);
    setError('');
    if (!turn) {
      scrollOnAnswer.current = true;
      setPendingQuestion(next);
    }
    try {
      const response = await researchApi.followup(runId, next, history, contextRunIds, Boolean(turn));
      if (!response.ok) {
        setError(response.error);
        return;
      }
      if (turn && response.data.plan) {
        const supplementId = response.data.plan.id;
        setTurns(current => current.map((entry, index) => index === supplementIndex ? { ...entry, supplementId } : entry));
      } else {
        scrollOnAnswer.current = true;
        setTurns(current => [...current, { question: next, history, contextRunId: runId, contextRunIds, answer: response.data }]);
        setQuestion('');
      }
    } catch {
      setError(turn ? '补查计划暂时无法显示，请检查连接后再试。' : '消息发送失败，已保留输入，可以重试。');
    } finally {
      setPendingQuestion('');
      setBusy(false);
    }
  }

  return <>
    {(last || pendingQuestion) && <section className="followup-history" hidden={!visible} aria-label="研究对话">
      {turns.map((turn, index) => <article key={index} className="followup-turn">
        <p className="research-user-message">{turn.question}</p>
        <div className="research-assistant-message">
          <p className="text-sm text-slate-600">{turn.answer.period && `${turn.answer.period} · `}{turn.answer.message}</p>
          {turn.answer.findings.map((finding, position) => <div className="mt-3" key={position}>
            <h4 className="text-sm font-medium">{finding.task}</h4>
            <FindingContent finding={finding} evidence={evidence} />
          </div>)}
          {turn.supplementId ? <FollowupResearch runId={turn.supplementId} onUpdate={rememberResearch} />
            : turn.answer.draft_goal && <Button className="mt-3" variant="outline"
              disabled={busy} onClick={() => void send(index)}>{turn.answer.draft_kind === 'market' ? '生成行情与估值补查计划' : '生成补查计划'}</Button>}
        </div>
      </article>)}
      {pendingQuestion && <article className="followup-turn">
        <p className="research-user-message">{pendingQuestion}</p>
        <p className="research-assistant-message text-sm text-slate-600" role="status">正在核对资料…</p>
      </article>}
      <div ref={tail} />
    </section>}
    <div className="followup-dock" hidden={!visible}>
      <form className="followup-form" aria-label="发送消息" onSubmit={event => {
        event.preventDefault();
        void send();
      }}>
        <div className="followup-input-row">
          <textarea aria-label="消息" rows={1} maxLength={450} readOnly={busy} value={question}
            onChange={event => setQuestion(event.target.value)} placeholder="发消息…"
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                event.preventDefault();
                void send();
              }
            }} />
          <Button type="submit" size="icon" aria-label="发送消息" disabled={busy || question.trim().length < 2}>
            <ArrowUp size={18} />
          </Button>
        </div>
        {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
      </form>
    </div>
  </>;
}
