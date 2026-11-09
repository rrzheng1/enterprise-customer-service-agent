import { expect, it } from 'vitest';
import { recoveryStatus } from './recovery';
import type { Workspace } from './client';
const workspace = (status: string): Workspace => ({ conversation: { id: 'c', tenant_id: 't', user_id: 'u', title: 'x', status: 'open', service_mode: 'bot' }, messages: [], pending_actions: [], tickets: [], runs: [{ id: 'r', request_id: 'request', status }] });
it('restores a disconnected request by its persisted ID, not by an older successful run', () => {
  expect(recoveryStatus(workspace('running'), { requestId: 'request', runId: 'r' })).toBe('pending');
  expect(recoveryStatus(workspace('success'), { requestId: 'request', runId: 'r' })).toBe('settled');
  expect(recoveryStatus(workspace('success'), { requestId: 'new-request', runId: null })).toBe('unknown');
  expect(recoveryStatus(workspace('waiting_confirmation'), { requestId: 'request', runId: 'r' })).toBe('settled');
});
it('recognizes a persisted human-mode message without inventing an Agent run', () => {
  const w = workspace('success'); w.conversation.service_mode = 'human';
  w.messages = [{ id: 'm', role: 'user', content: '补充信息', metadata: { idempotency_key: 'human-request' } }];
  expect(recoveryStatus(w, { requestId: 'human-request', runId: null })).toBe('settled');
  expect(recoveryStatus(w, { requestId: 'other-request', runId: null })).toBe('unknown');
});
