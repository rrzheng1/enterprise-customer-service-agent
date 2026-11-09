import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request, setAccessToken, query } from './client';
afterEach(() => { vi.unstubAllGlobals(); setAccessToken(''); });
describe('API transport', () => {
  it('sends verified bearer identity without storing it or placing it in the URL', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ answer: 'ok' })));
    vi.stubGlobal('fetch', fetcher); setAccessToken('test-session-token');
    await request('/api/v1/chat', { question: 'hello' });
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/chat');
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer test-session-token');
    expect(fetcher.mock.calls[0][1].method).toBe('POST');
  });
  it('never turns a failed approval into a successful result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: '条件变化' }), { status: 409 })));
    await expect(request('/confirmations/x/approve', {})).rejects.toMatchObject({ status: 409, message: '条件变化' });
  });
  it('handles unavailable and non-JSON services', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('unavailable', { status: 503 })));
    await expect(request('/api')).rejects.toBeInstanceOf(ApiError);
  });
  it('escapes user and tenant query values', () => {
    expect(new URLSearchParams(query({ user_id: 'a&tenant_id=b' })).get('user_id')).toBe('a&tenant_id=b');
  });
});
