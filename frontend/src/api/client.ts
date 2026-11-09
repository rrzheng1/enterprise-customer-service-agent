import type { components } from './schema';
export type Schema<K extends keyof components['schemas']> = components['schemas'][K];
export type Session = Schema<'SessionView'>;
export type Conversation = Schema<'ConversationView'>;
export type Workspace = Schema<'ConversationWorkspaceView'>;
export type Reply = Schema<'ChatResponse'>;
export type Action = Schema<'PendingActionView'>;
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
// Credentials stay in memory, never in source, URLs or browser storage.
let accessToken = '';
export function setAccessToken(value: string) { accessToken = value.trim(); }
export const authenticatedHeaders = (): Record<string, string> => accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
export async function request<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { method: body === undefined ? 'GET' : 'POST', signal,
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const messages: Record<string, string> = { not_found: '会话或记录不存在，或不属于当前账号。', permission_denied: '当前身份无权执行此操作，请检查账号角色或登录凭证。', authentication_required: '需要有效的身份凭证才能访问。', conversation_closed: '此会话已结束，请新建会话继续。', operation_uncertain: '操作结果尚未确认，请刷新工单记录核实，避免重复提交。', approval_conditions_changed: '业务条件已变化，当前申请无法继续，请重新核实。' };
    throw new ApiError(response.status, messages[data?.code] || data?.message || (typeof data?.detail === 'string' ? data.detail : `请求失败（${response.status}），请检查输入或稍后重试。`));
  }
  return data as T;
}
export const identity = (s: Session) => ({ tenant_id: s.tenant_id, user_id: s.user_id });
export const query = (data: Record<string, string>) => new URLSearchParams(data).toString();
export const describeError = (e: unknown) => e instanceof Error ? e.message : '请求失败，请检查服务连接。';
export const actionName = (tool: string) => ({ create_refund_case: '退款申请', create_exchange_case: '换货申请', transfer_to_human: '转接人工客服', create_compensation_case: '补偿申请' }[tool] || '售后申请');
