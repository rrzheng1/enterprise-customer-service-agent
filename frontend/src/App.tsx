import { useEffect, useState } from 'react';
import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { MessageCircle, Headphones, FlaskConical } from 'lucide-react';
import { request, describeError, setAccessToken, type Session, type Schema } from './api/client';
import Chat from './pages/Chat';
import Operations from './pages/Operations';

function WorkspaceApp() {
  const location = useLocation(); const operations = location.pathname.startsWith('/operations');
  const [session, setSession] = useState<Session | null>(null); const [error, setError] = useState('');
  const [token, setToken] = useState(''); const [attempt, setAttempt] = useState(0); const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setSession(null); setError('');
    request<Schema<'UIConfigView'>>('/ui/config', undefined, controller.signal).then(c => request<Session>(`${c.api_prefix}/session?workspace=${operations ? 'operations' : 'customer'}`, undefined, controller.signal)).then(s => { if (!controller.signal.aborted) setSession(s); }).catch(e => { if (!controller.signal.aborted) setError(describeError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [operations, attempt]);
  return <div className="app"><nav className="global-nav"><NavLink to="/chat" className="brand"><span>知</span><strong>知序<small>企业智能客服</small></strong></NavLink><div className="nav-links"><NavLink to="/chat"><MessageCircle size={17}/> 客户服务</NavLink><NavLink to="/operations"><Headphones size={17}/> 运营工作台</NavLink><NavLink to="/demo"><FlaskConical size={17}/> 场景验证</NavLink></div><div className="account">{session?.display_name || '安全工作空间'}{session?.development_mode && <span className="dev-badge">本地演示</span>}</div></nav>
    {loading ? <div className="loading">正在连接服务并验证身份…</div> : !session ? <main className="login panel"><h1>连接工作空间</h1><p>生产部署请使用身份服务签发的访问令牌。令牌只保存在当前页面内存中。</p><div className="error" role="alert">{error}</div><form onSubmit={e => { e.preventDefault(); setAccessToken(token); setToken(''); setAttempt(a => a + 1); }}><label>访问令牌<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} required/></label><button>验证并进入</button></form><NavLink to="/chat">返回客户服务</NavLink></main> : <><Routes><Route path="/" element={<Chat session={session}/>}/><Route path="/chat" element={<Chat session={session}/>}/><Route path="/chat/:conversationId" element={<Chat session={session}/>}/><Route path="/operations" element={<Operations session={session}/>}/><Route path="/demo" element={<main className="page demo"><p className="eyebrow">DEMO LAB</p><h1>业务场景验证台</h1><p>使用 seed_sample_data.py 中的真实演示订单，验证查询、知识检索、多轮对话、权限隔离与审批。</p><div className="demo-scenarios">{[['202606040001', '未签收 · 阻断退款'], ['202606040002', '已签收 · 审核证据不足'], ['202606040003', '预审核通过 · 确认后创建 MCP 工单']].map(([id, title]) => <div className="panel" key={id}><code>{id}</code><h3>{title}</h3></div>)}</div><a className="button" href="/demo/legacy" target="_blank" rel="noreferrer">独立打开完整验证台 ↗</a><iframe title="场景验证台" src="/demo/legacy"/></main>}/><Route path="*" element={<main className="page"><h1>页面不存在</h1><NavLink to="/chat">返回客服</NavLink></main>}/></Routes></>}
  </div>;
}
export default function App() { return <BrowserRouter><WorkspaceApp/></BrowserRouter>; }
