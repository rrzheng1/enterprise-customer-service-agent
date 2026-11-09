import { statusText, utcTime } from '../api/presentation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Reply, Action, Schema } from '../api/client';
import { actionName } from '../api/client';
import { useNow } from '../hooks/useNow';

export function Message({ message, response }: { message: Schema<'ConversationMessageView'>; response?: Reply }) {
  return <article className={`message ${message.role}`}>
    <div className="avatar">{message.role === 'user' ? '我' : '知'}</div>
    <div className="message-body"><div className="message-label">{message.role === 'user' ? '你' : '知序智能客服'}</div>
      <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{response?.pending_confirmation && message.content === response.answer || (message.role === 'assistant' && message.content.includes('工具名称：') && message.content.includes('风险等级：')) ? '本轮申请涉及业务操作，请查看确认卡片及后续处理结果。' : message.content}</ReactMarkdown></div>
      {response?.tool_results?.length ? <div className="business-progress">{response.tool_results.map((r, i) => <span key={i}>{r.ok ? '✓' : '!'} {r.name.startsWith('query_') ? '业务信息查询' : r.name === 'check_refund_eligibility' ? '售后条件核实' : actionName(r.name)} · {r.outcome?.business_status === 'not_satisfied' ? '条件未满足' : r.ok ? '已返回结果' : '执行失败'}</span>)}</div> : null}
      {response?.knowledge?.length ? <details className="sources"><summary>参考了 {response.knowledge.length} 条知识来源</summary>{response.knowledge.map(k => <div key={k.id}><strong>{k.title || k.source}</strong><p>{k.content}</p><small>{k.source}</small></div>)}</details> : null}
    </div>
  </article>;
}
export function ConfirmationCard({ action, busy, onDecision }: { action: Action; busy: boolean; onDecision: (a: Action, d: 'approve' | 'reject') => void }) {
  const now = useNow();
  const expired = action.expired || (!!action.expires_at && utcTime(action.expires_at) <= now);
  return <section className="confirmation" aria-label="操作确认">
    <div className="eyebrow">{expired ? '确认已过期' : '等待你的确认'}</div><h3>{actionName(action.tool_name)}</h3>
    <dl><dt>操作类型</dt><dd>{actionName(action.tool_name)}</dd>{['order_id', 'reason', 'refund_type', 'amount'].map(key => action.arguments?.[key] == null ? null : <div className="detail-row" key={key}><dt>{{ order_id: '订单号', reason: '申请原因', refund_type: '退款方式', amount: '金额' }[key]}</dt><dd>{statusText(String(action.arguments?.[key]))}</dd></div>)}</dl>
    <p>请核对以上申请信息，确认后提交处理。</p><small>批准后仍需通过业务校验。请以系统返回的工单与执行结果为准。</small>
    {expired && <p>本次确认已失效，请新建会话重新核实业务条件。</p>}
    <div className="actions"><button disabled={busy || expired} onClick={() => onDecision(action, 'approve')}>确认提交</button><button className="secondary" disabled={busy || expired} onClick={() => onDecision(action, 'reject')}>取消申请</button></div>
  </section>;
}
