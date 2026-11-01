import { privateFetch } from './identity';

// Fetch streaming supports bearer auth; native EventSource cannot set that header.
export async function consumeResearchEvents(id: string, after: number, signal: AbortSignal, onEvent: (cursor: number) => void) {
  const response = await privateFetch(`/api/v1/runs/${encodeURIComponent(id)}/events/stream?after_id=${after}`, { signal, headers: { Accept: 'text/event-stream' } });
  if (!response.ok || !response.body) throw new Error('研究进度连接暂不可用');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const message = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const cursor = Number(message.match(/^id: (\d+)$/m)?.[1]);
        if (Number.isSafeInteger(cursor) && cursor > after) { after = cursor; onEvent(cursor); }
        if (message.includes('event: stream.closed')) { onEvent(after); return; }
      }
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
