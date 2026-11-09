import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Plus, Send, RefreshCw, MessageSquare } from 'lucide-react';
import { request, identity, query, describeError, actionName, type Action, type Conversation, type Schema, type Session, type Workspace } from '../api/client';
import { restoredThread, statusText } from '../api/presentation';
import { streamRequest, applyStreamEvent, initialStreamState, isRejectedStreamRequest } from '../api/stream';
import { pendingRequest, recoveryStatus, rememberRequest } from '../api/recovery';
import { Message, ConfirmationCard } from '../components/Message';

const nodeLabels: Record<string, string> = { prepare: '会话与业务上下文已准备', rewrite: '问题理解已完成', clarify: '需要补充信息', retrieve: '知识查询已完成', evaluate_retrieval: '知识依据已检查', decide: '处理方案已确定', execute_plan_step: '业务步骤已处理', execute_tool_call: '业务查询已处理', create_pending_action: '申请信息已保存', finalize: '答复已生成', persist: '服务记录已保存' };
type Operation = { id: string | undefined; controller: AbortController };

export default function Chat({ session: s }: { session: Session }) {
  const { conversationId } = useParams(); const navigate = useNavigate();
  const [list, setList] = useState<Conversation[]>([]); const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [text, setText] = useState(''); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(false);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [optimistic, setOptimistic] = useState('');
  const [stream, setStream] = useState(initialStreamState); const [uncertain, setUncertain] = useState(false);
  const active = useRef<Operation | null>(null); const epoch = useRef(0); const tail = useRef<HTMLDivElement>(null);
  const base = s.api_prefix; const own = identity(s);
  const reloadList = useCallback(async () => setList(await request<Conversation[]>(`${base}/conversations?${query(identity(s))}`)), [base, s]);
  const load = useCallback((id: string, signal?: AbortSignal) => request<Workspace>(`${base}/conversations/${encodeURIComponent(id)}/workspace?${query(identity(s))}`, undefined, signal), [base, s]);
  const restore = useCallback((w: Workspace) => {
    setWorkspace(w); const status = recoveryStatus(w, pendingRequest(s, w.conversation.id)); setUncertain(status !== 'settled');
    if (status === 'settled') rememberRequest(s, w.conversation.id, null);
    return status;
  }, [s]);
  useEffect(() => { reloadList().catch(e => setError(describeError(e))); }, [reloadList]);
  useEffect(() => {
    const version = ++epoch.current; const controller = new AbortController();
    const ownStream = active.current?.id === conversationId && !!active.current;
    if (!ownStream) { active.current?.controller.abort(); active.current = null; setBusy(false); setStream(initialStreamState()); setOptimistic(''); setUncertain(false); }
    setError(''); setNotice(''); setWorkspace(null);
    if (!conversationId) { setLoading(false); return; }
    setLoading(true);
    load(conversationId, controller.signal).then(w => { if (version === epoch.current) { if (ownStream) setWorkspace(w); else restore(w); } }).catch(e => { if (!controller.signal.aborted && version === epoch.current) setError(describeError(e)); }).finally(() => { if (!controller.signal.aborted && version === epoch.current) setLoading(false); });
    return () => controller.abort();
  }, [conversationId, load, restore]);
  useEffect(() => () => { active.current?.controller.abort(); active.current = null; }, []);
  // GET-only recovery: no reconnection path re-POSTs messages or resumes approvals.
  useEffect(() => {
    if (!conversationId || !workspace || busy || (!uncertain && workspace.conversation.service_mode === 'bot')) return;
    const controller = new AbortController(); let inFlight = false;
    const timer = window.setInterval(async () => {
      if (inFlight) return; inFlight = true;
      try { const w = await load(conversationId, controller.signal); if (!controller.signal.aborted) { const status = restore(w); if (status === 'settled' && uncertain) { setOptimistic(''); setStream(initialStreamState()); setNotice('已重新读取服务记录，请以当前消息、审批状态与工单为准。'); } } }
      catch (e) { if (!controller.signal.aborted) setError(describeError(e)); }
      finally { inFlight = false; }
    }, 3000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [conversationId, load, restore, workspace?.conversation.service_mode, uncertain, busy]);
  useEffect(() => { tail.current?.scrollIntoView({ block: 'end' }); }, [workspace?.messages.length, optimistic, stream.answer, stream.nodes.length]);

  function go(path: string) {
    const wasActive = !!active.current;
    active.current?.controller.abort(); active.current = null; setBusy(false); setOptimistic(''); setStream(initialStreamState());
    if (conversationId && path === `/chat/${conversationId}`) { if (wasActive) setUncertain(true); void refresh(); }
    else navigate(path);
  }
  async function refresh() { try { if (conversationId) { const status = restore(await load(conversationId)); if (status === 'settled') { setStream(initialStreamState()); setOptimistic(''); } } await reloadList(); } catch (e) { setError(describeError(e)); } }
  async function send() {
    const question = text.trim(); if (!question || busy || loading || uncertain || workspace?.pending_actions.some(a => a.status === 'pending') || workspace?.conversation.status === 'closed') return;
    const op: Operation = { id: conversationId, controller: new AbortController() }; active.current = op;
    setBusy(true); setError(''); setNotice(''); setOptimistic(question); setText(''); setStream(initialStreamState());
    const requestId = crypto.randomUUID(); let current = initialStreamState();
    try {
      if (!op.id) {
        const created = await request<Conversation>(`${base}/conversations`, { ...own, title: question.slice(0, 24) }, op.controller.signal);
        if (active.current !== op) return;
        op.id = created.id; navigate(`/chat/${op.id}`);
      }
      rememberRequest(s, op.id, { requestId, runId: null });
      await streamRequest(`${base}/chat/stream`, { ...own, conversation_id: op.id, thread_id: restoredThread(workspace), question, metadata: { idempotency_key: requestId } }, event => {
        if (active.current !== op) return;
        if (event.conversation_id && event.conversation_id !== op.id) throw new Error('服务返回了不匹配的会话');
        current = applyStreamEvent(current, event); setStream(current);
        if (event.run_id) rememberRequest(s, op.id!, { requestId, runId: event.run_id });
      }, op.controller.signal);
      if (active.current !== op) return;
      if (current.terminal !== 'completed') throw new Error(current.error || '执行结果需核实');
      if (!current.runId) rememberRequest(s, op.id, null); // Persisted human-mode acknowledgement, no AgentRun.
      const w = await load(op.id); if (active.current !== op) return;
      restore(w); setOptimistic(''); setStream(initialStreamState()); await reloadList();
      if (active.current === op) setNotice(w.pending_actions.length ? '等待你的确认' : '本次处理已结束，服务记录已更新。');
    } catch (e) {
      if (active.current !== op) return;
      if (isRejectedStreamRequest(e)) {
        if (op.id) rememberRequest(s, op.id, null);
        setOptimistic(''); setUncertain(false); setError(describeError(e)); return;
      }
      setError(op.controller.signal.aborted ? '已停止接收。后台可能继续处理，这不代表业务已撤销；正在核实保存的记录。' : `${describeError(e)}。不会自动重发，正在核实保存的记录。`);
      setUncertain(true);
      if (op.id) { try { const w = await load(op.id); if (active.current === op) { const status = restore(w); if (status === 'settled') { setOptimistic(''); setStream(initialStreamState()); } } } catch { /* Stay uncertain if GET also fails. */ } }
    } finally { if (active.current === op) { active.current = null; setBusy(false); } }
  }
  async function decide(a: Action, decision: 'approve' | 'reject') {
    if (busy || uncertain) return; setBusy(true); setError(''); setNotice('正在提交决定并核实执行结果…'); const version = epoch.current;
    try { const r = await request<Schema<'ConfirmationDecisionResponse'>>(`${base}/confirmations/${encodeURIComponent(a.id)}/${decision}`, own); if (version !== epoch.current) return; setNotice(r.answer || r.message); if (conversationId) restore(await load(conversationId)); await reloadList(); }
    catch (e) { if (version !== epoch.current) return; setError(`${describeError(e)}。请刷新记录核实实际状态，批准不等于业务成功。`); if (conversationId) { try { restore(await load(conversationId)); } catch { setUncertain(true); } } }
    finally { if (version === epoch.current) setBusy(false); }
  }
  const pending = workspace?.pending_actions.filter(a => a.status === 'pending') || [];
  const savedAnswer = workspace?.messages.some(m => m.role === 'assistant' && m.metadata?.run_id === stream.runId);
  const savedQuestion = workspace?.messages.some(m => m.role === 'user' && m.content === optimistic);
  const navigationBlocked = busy && !active.current;
  return <div className="chat-layout"><aside className="conversation-sidebar"><div className="sidebar-heading">我的会话<button className="icon secondary" aria-label="刷新会话" onClick={() => void refresh()}><RefreshCw size={15}/></button></div>
    <button className="new-chat" disabled={navigationBlocked} onClick={() => go('/chat')}><Plus size={17}/> 新建会话</button><div className="conversation-list">{list.map(c => <button disabled={navigationBlocked} key={c.id} className={`conversation ${conversationId === c.id ? 'active' : ''}`} onClick={() => go(`/chat/${c.id}`)}><MessageSquare size={16}/><span>{c.title || '新会话'}<small>{c.service_mode === 'bot' ? '智能客服' : '人工协同'} · {c.status === 'closed' ? '已结束' : '进行中'}</small></span></button>)}{!list.length && <p className="muted">还没有会话，开始一次咨询吧。</p>}</div><div className="sidebar-footer">咨询与售后，一处处理<br/><small>会话记录由服务端保存</small></div></aside>
    <section className="chat-main"><header className="chat-header"><div><h1>{workspace?.conversation.title || '智能客服'}</h1><p>{workspace?.conversation.service_mode && workspace.conversation.service_mode !== 'bot' ? '人工服务中 · 消息定时刷新' : '订单、政策与售后服务'}</p></div><span className="status"><i/> {uncertain ? '正在核实记录' : busy ? '正在处理' : '服务已连接'}</span></header>
    <div className="chat-scroll" aria-live="polite">{loading && <p className="loading">正在恢复会话…</p>}{!conversationId && <div className="welcome"><div className="welcome-icon">知</div><p className="eyebrow">知序 · 客户服务</p><h2>你好，有什么可以帮你？</h2><p>查询订单进度，了解服务政策，或提交售后申请。<br/>涉及业务操作时，我们会先与你确认。</p><div className="suggestions">{['查询订单 202606040001 的物流进度', '商品有质量问题，售后需要准备什么？', '我想了解退换货政策'].map(q => <button className="secondary" key={q} onClick={() => setText(q)}>{q}</button>)}</div></div>}
      {workspace?.messages.filter(m => m.role === 'user' || m.role === 'assistant').map(m => <Message key={m.id} message={m} response={workspace.responses?.[String(m.metadata?.run_id)]}/>)}
      {optimistic && !savedQuestion && <Message message={{ id: 'sending', role: 'user', content: optimistic, metadata: {} }}/>}
      {(stream.nodes.length > 0 || Object.keys(stream.tools).length > 0) && <section className="stream-progress" aria-label="实时执行进度"><p>{nodeLabels[stream.nodes.at(-1) || ''] || '正在处理业务'}</p>{Object.entries(stream.tools).map(([id, t]) => <small key={id}>{t.name.startsWith('query_') ? '业务信息查询' : t.name === 'check_refund_eligibility' ? '售后条件核实' : actionName(t.name)} · {t.status === 'running' ? '执行中' : t.status === 'not_satisfied' ? '条件未满足' : statusText(t.status)}</small>)}</section>}
      {stream.answer && !savedAnswer && <div data-testid="streaming-answer"><Message message={{ id: 'streaming', role: 'assistant', content: stream.answer, metadata: {} }}/><small className="muted">{stream.terminal ? '正在同步保存的服务记录' : '正在生成答复，最终以保存记录为准'}</small></div>}
      {!!stream.knowledge.length && !savedAnswer && <details className="sources"><summary>已检索到 {stream.knowledge.length} 条知识来源</summary>{stream.knowledge.map(k => <div key={k.id}><strong>{k.title}</strong><p>{k.content}</p><small>{k.source}</small></div>)}</details>}
      {busy && <div className="processing" role="status"><span className="spinner"/>{active.current ? '正在接收实时处理结果…' : '正在核实业务执行结果…'}{active.current && <button className="secondary" onClick={() => active.current?.controller.abort()}>停止接收</button>}</div>}
      {uncertain && <div className="notice" role="status">执行尚未结束或结果待核实，页面只读取保存记录，不会自动重发。停止接收、切换会话和关闭页面均不代表撤销业务。</div>}
      {pending.map(a => <ConfirmationCard key={a.id} action={a} busy={busy || uncertain} onDecision={decide}/>)}
      {workspace?.tickets.length ? <section className="ticket-results"><h3>已记录的服务工单</h3>{workspace.tickets.map(t => <div key={t.id}><strong>{t.title}</strong><p>工单号：<code>{t.id}</code></p><small>当前状态：{statusText(t.status)} {t.order_id ? ` · 订单 ${t.order_id}` : ''}</small></div>)}</section> : null}
      {notice && <div className="notice" role="status">{notice}</div>}{error && <div className="error" role="alert">{error}<button className="secondary" onClick={() => void refresh()}>刷新记录</button></div>}<div ref={tail}/></div>
    <form className="composer" onSubmit={e => { e.preventDefault(); void send(); }}><div className="input-shell"><textarea aria-label="消息" placeholder={pending.length ? '请先处理上方待确认申请' : uncertain ? '结果待核实，请刷新记录或新建会话' : '输入你的问题…'} value={text} maxLength={8000} disabled={busy || loading || uncertain || pending.length > 0 || workspace?.conversation.status === 'closed'} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }}/><button aria-label="发送消息" disabled={busy || loading || uncertain || !text.trim() || pending.length > 0 || workspace?.conversation.status === 'closed'}><Send size={18}/></button></div><small>Enter 发送 · Shift + Enter 换行　｜　重要操作将再次征求确认</small></form>
    </section></div>;
}
