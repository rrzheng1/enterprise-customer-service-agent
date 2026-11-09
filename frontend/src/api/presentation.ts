import type { Workspace } from './client';
export const utcTime = (value: string) => new Date(/[zZ]$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`).getTime();
export const statusText = (value: string) => ({ unknown: '结果待核实', success: '成功', error: '错误', completed: '已完成', pending: '待确认', approved: '已批准', executed: '已执行', rejected: '已取消', failed: '失败', running: '处理中', waiting_confirmation: '等待确认', waiting_assignment: '待分配', assigned: '已接管', in_service: '服务中', resolution_submitted: '待审核结论', resolved: '已解决', cancelled: '已取消', open: '进行中', active: '进行中', closed: '已关闭', bot: '智能客服', human: '人工客服', human_pending: '等待人工', expired: '已过期', return_refund: '退货退款', refund_only: '仅退款' }[value] || value);
export function restoredThread(workspace: Workspace | null): string | null {
  if (!workspace) return null;
  // Message metadata also covers old conversations whose run is beyond the recent run window.
  for (const m of [...workspace.messages].reverse()) {
    if (typeof m.metadata?.thread_id === 'string') return m.metadata.thread_id;
  }
  return Object.values(workspace.responses || {}).find(r => r.thread_id)?.thread_id || null;
}
