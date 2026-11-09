import { expect, it } from 'vitest';
import { restoredThread, utcTime } from './presentation';
it('interprets timezone-less MySQL timestamps as UTC', () => {
  expect(utcTime('2026-11-09T06:23:12')).toBe(Date.parse('2026-11-09T06:23:12Z'));
  expect(utcTime('2026-11-09T14:23:12+08:00')).toBe(Date.parse('2026-11-09T06:23:12Z'));
});
it('restores the backend thread from persisted metadata without inventing an ID', () => {
  expect(restoredThread(null)).toBeNull();
  expect(restoredThread({ conversation: { id: 'c', tenant_id: 't', user_id: 'u', title: 'x', status: 'open', service_mode: 'bot' }, messages: [{ id: 'm', role: 'assistant', content: 'hi', metadata: { thread_id: 'server-thread' } }], pending_actions: [], tickets: [] })).toBe('server-thread');
});
