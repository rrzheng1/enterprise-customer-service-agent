import { ApiError, authenticatedHeaders, type Schema } from './client';
export type StreamEvent = Schema<'StreamEvent'>;
export const isRejectedStreamRequest = (e: unknown) => e instanceof ApiError && [400, 401, 403, 404, 409, 422, 429].includes(e.status);
const eventTypes = new Set(['run_started', 'node_completed', 'knowledge_ready', 'tool_started', 'tool_completed', 'answer_delta', 'confirmation_required', 'run_completed', 'run_failed', 'stream_interrupted', 'heartbeat']);

/** Incremental UTF-8 + SSE parser, including CRLF split across chunks and multiline data. */
export class SSEDecoder {
  private decoder = new TextDecoder('utf-8', { fatal: true });
  private buffer = ''; private data: string[] = []; private id = ''; private type = '';
  constructor(private onEvent: (event: StreamEvent) => void) {}
  push(chunk: Uint8Array) { this.buffer += this.decoder.decode(chunk, { stream: true }); this.consume(false); }
  finish() {
    this.buffer += this.decoder.decode(); this.consume(true);
    // SSE only dispatches blank-line-terminated frames. An incomplete tail is not a success.
    if (this.buffer.trim() || this.data.length) throw new Error('流式响应在完整事件到达前中断');
  }
  private consume(final: boolean) {
    if (this.buffer.length + this.data.join('').length > 1024 * 1024) throw new Error('流式事件过大');
    let index = 0;
    while (index < this.buffer.length) {
      const c = this.buffer[index];
      if (c !== '\r' && c !== '\n') { index++; continue; }
      if (c === '\r' && index === this.buffer.length - 1 && !final) break;
      const line = this.buffer.slice(0, index); const skip = c === '\r' && this.buffer[index + 1] === '\n' ? 2 : 1;
      this.buffer = this.buffer.slice(index + skip); index = 0; this.line(line);
    }
  }
  private line(line: string) {
    if (!line) {
      if (this.data.length) {
        const event = JSON.parse(this.data.join('\n')) as StreamEvent;
        if (!event || !eventTypes.has(event.event_type) || !Number.isInteger(event.sequence) || event.sequence < 1 ||
          typeof event.event_id !== 'string' || typeof event.timestamp !== 'string' || !event.payload ||
          this.id !== event.event_id || (this.type && this.type !== event.event_type)) throw new Error('流式事件契约不匹配');
        this.onEvent(event);
      }
      this.data = []; this.id = ''; this.type = ''; return;
    }
    if (line.startsWith(':')) return;
    const separator = line.indexOf(':'); const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? '' : line.slice(separator + 1); if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'data') this.data.push(value); else if (field === 'id') this.id = value; else if (field === 'event') this.type = value;
  }
}

export async function streamRequest(url: string, body: unknown, onEvent: (e: StreamEvent) => void, signal: AbortSignal) {
  const response = await fetch(url, { method: 'POST', signal, headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...authenticatedHeaders() }, body: JSON.stringify(body) });
  if (!response.ok) throw new ApiError(response.status, `流式请求未被接受（${response.status}），请检查身份或服务状态。`);
  if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) throw new Error('服务未返回有效 SSE 响应');
  const reader = response.body.getReader(); let terminal = false;
  const decoder = new SSEDecoder(event => { onEvent(event); if (['run_completed', 'run_failed', 'stream_interrupted'].includes(event.event_type)) terminal = true; });
  try {
    while (!terminal) { const { done, value } = await reader.read(); if (done) { decoder.finish(); break; } decoder.push(value); }
    if (!terminal) throw new Error('连接已断开，执行结果尚未确认');
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

export interface StreamState {
  lastSequence: number; seen: Set<string>; runId: string | null; conversationId: string | null; threadId: string | null;
  answer: string; nodes: string[]; tools: Record<string, { name: string; status: string }>;
  terminal: 'completed' | 'failed' | 'interrupted' | null; error: string;
  knowledge: Schema<'PublicKnowledge'>[];
}
export const initialStreamState = (): StreamState => ({ lastSequence: 0, seen: new Set(), runId: null, conversationId: null, threadId: null,
  answer: '', nodes: [], tools: {}, terminal: null, error: '', knowledge: [] });
export function applyStreamEvent(state: StreamState, event: StreamEvent): StreamState {
  if (state.terminal || state.seen.has(event.event_id) || event.sequence <= state.lastSequence) return state;
  if (state.runId && event.run_id && state.runId !== event.run_id) throw new Error('流式运行身份变化，请重新核实会话');
  const next = { ...state, seen: new Set(state.seen).add(event.event_id), lastSequence: event.sequence,
    runId: event.run_id || state.runId, conversationId: event.conversation_id || state.conversationId, threadId: event.thread_id || state.threadId };
  const p = event.payload;
  switch (event.event_type) {
    case 'answer_delta': if ('text' in p) next.answer += p.text; break;
    case 'node_completed': if ('node' in p) next.nodes = [...state.nodes, p.node]; break;
    case 'tool_started': case 'tool_completed': if ('call_id' in p) next.tools = { ...state.tools, [p.call_id]: { name: p.tool, status: event.event_type === 'tool_started' ? 'running' : p.execution_status === 'success' ? p.business_status === 'not_satisfied' ? 'not_satisfied' : 'completed' : 'failed' } }; break;
    case 'knowledge_ready': if ('knowledge' in p) next.knowledge = p.knowledge; break;
    case 'run_completed': if ('answer' in p) { next.answer = p.answer; next.terminal = 'completed'; } break;
    case 'run_failed': case 'stream_interrupted': next.terminal = event.event_type === 'run_failed' ? 'failed' : 'interrupted'; next.error = '执行结果需核实，请读取已保存的会话与工单记录。'; break;
  }
  return next;
}
