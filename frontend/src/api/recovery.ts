import type { Session, Workspace } from './client';
export interface PendingRequest { requestId: string; runId: string | null }
const key = (s: Session, conversation: string) => `agent-pending:${s.tenant_id}:${s.user_id}:${conversation}`;
export function rememberRequest(s: Session, conversation: string, pending: PendingRequest | null) {
  try { if (pending) sessionStorage.setItem(key(s, conversation), JSON.stringify(pending)); else sessionStorage.removeItem(key(s, conversation)); } catch { /* Recovery also uses server run records when storage is unavailable. */ }
}
export function pendingRequest(s: Session, conversation: string): PendingRequest | null {
  try { return JSON.parse(sessionStorage.getItem(key(s, conversation)) || 'null'); } catch { return null; }
}
export function recoveryStatus(workspace: Workspace, pending: PendingRequest | null): 'pending' | 'settled' | 'unknown' {
  const run = pending ? workspace.runs?.find(r => r.id === pending.runId || r.request_id === pending.requestId) : workspace.runs?.[0];
  if (!run) {
    // Human-mode sends persist the accepted customer message without creating an AgentRun.
    if (pending && workspace.conversation.service_mode !== 'bot' && workspace.messages.some(m =>
      m.role === 'user' && m.metadata?.idempotency_key === pending.requestId)) return 'settled';
    return pending ? 'unknown' : 'settled';
  }
  return run.status === 'running' || run.error_code === 'stream_shutdown_unknown' ? 'pending' : 'settled';
}
