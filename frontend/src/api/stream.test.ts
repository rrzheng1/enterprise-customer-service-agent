import { afterEach, describe, expect, it, vi } from 'vitest';
import { SSEDecoder, applyStreamEvent, initialStreamState, streamRequest, isRejectedStreamRequest, type StreamEvent } from './stream';
import { ApiError } from './client';
const event = (sequence: number, event_type: StreamEvent['event_type'], payload: StreamEvent['payload']): StreamEvent => ({ event_id: `s:${sequence}`, sequence, event_type, payload, run_id: 'run', conversation_id: 'c', thread_id: 't', timestamp: '2026-11-09T00:00:00Z' });
const frame = (e: StreamEvent) => `id: ${e.event_id}\r\nevent: ${e.event_type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`;
afterEach(() => vi.unstubAllGlobals());
describe('SSE framing and truthful rendering', () => {
  it('distinguishes a rejected request from an uncertain network/server failure', () => {
    expect(isRejectedStreamRequest(new ApiError(403, 'denied'))).toBe(true);
    expect(isRejectedStreamRequest(new ApiError(422, 'invalid'))).toBe(true);
    expect(isRejectedStreamRequest(new ApiError(503, 'unavailable'))).toBe(false);
    expect(isRejectedStreamRequest(new TypeError('network'))).toBe(false);
  });
  it('decodes Chinese UTF-8 and CRLF across every byte boundary', () => {
    const e = event(1, 'answer_delta', { text: '你好，退款申请' }); const events: StreamEvent[] = [];
    const decoder = new SSEDecoder(e => events.push(e));
    for (const byte of new TextEncoder().encode(frame(e))) decoder.push(new Uint8Array([byte]));
    decoder.finish(); expect(events).toEqual([e]);
  });
  it('supports multiline JSON data and comments with multiple frames per chunk', () => {
    const e = event(1, 'node_completed', { node: 'prepare' }); const events: StreamEvent[] = [];
    const text = `: heartbeat\nid: s:1\nevent: node_completed\n${JSON.stringify(e, null, 2).split('\n').map(l => 'data: ' + l).join('\n')}\n\n` + frame(event(2, 'heartbeat', {}));
    const decoder = new SSEDecoder(e => events.push(e)); decoder.push(new TextEncoder().encode(text)); decoder.finish();
    expect(events.length).toBe(2); expect(events[0]).toEqual(e);
  });
  it('rejects malformed JSON, mismatched event IDs, and incomplete frames', () => {
    expect(() => new SSEDecoder(() => {}).push(new TextEncoder().encode('data: invalid\n\n'))).toThrow();
    expect(() => new SSEDecoder(() => {}).push(new TextEncoder().encode(frame(event(1, 'heartbeat', {})).replace('id: s:1', 'id: other')))).toThrow();
    const decoder = new SSEDecoder(() => {}); decoder.push(new TextEncoder().encode('data: {')); expect(() => decoder.finish()).toThrow();
  });
  it('deduplicates events and replaces accumulated text with the single final answer', () => {
    const first = event(1, 'answer_delta', { text: '你' }); const second = event(2, 'answer_delta', { text: '好' });
    let state = applyStreamEvent(initialStreamState(), first); state = applyStreamEvent(state, first); state = applyStreamEvent(state, second);
    expect(state.answer).toBe('你好'); state = applyStreamEvent(state, event(3, 'run_completed', { answer: '你好', status: 'completed', persisted: true }));
    expect(state.answer).toBe('你好'); expect(state.terminal).toBe('completed');
    expect(applyStreamEvent(state, event(4, 'answer_delta', { text: 'late' }))).toBe(state);
  });
  it('keeps partial output uncertain after a failed run and rejects another run identity', () => {
    const state = applyStreamEvent(initialStreamState(), event(1, 'answer_delta', { text: '未保存' }));
    expect(() => applyStreamEvent(state, { ...event(2, 'heartbeat', {}), run_id: 'other' })).toThrow();
    const failed = applyStreamEvent(state, event(2, 'run_failed', { code: 'x', message: 'x', status: 'failed' }));
    expect(failed.answer).toBe('未保存'); expect(failed.terminal).toBe('failed');
  });
  it('does not retry POST after abrupt network EOF', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(frame(event(1, 'run_started', { status: 'running' })), { headers: { 'Content-Type': 'text/event-stream' } }));
    vi.stubGlobal('fetch', fetcher);
    await expect(streamRequest('/chat/stream', {}, () => {}, new AbortController().signal)).rejects.toThrow('连接已断开');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('passes abort signal and stops at an actual terminal event', async () => {
    const controller = new AbortController(); const fetcher = vi.fn().mockResolvedValue(new Response(frame(event(1, 'run_completed', { status: 'completed', answer: '完成', persisted: true })), { headers: { 'Content-Type': 'text/event-stream' } }));
    vi.stubGlobal('fetch', fetcher); const seen: StreamEvent[] = [];
    await streamRequest('/chat/stream', {}, e => seen.push(e), controller.signal);
    expect(fetcher.mock.calls[0][1].signal).toBe(controller.signal); expect(seen.length).toBe(1);
  });
});
