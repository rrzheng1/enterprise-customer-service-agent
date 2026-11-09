// Public screenshots from a fresh, independent demo stack. Never capture the developer's 8002 history.
const { chromium } = require('../.local-tools/browser/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.CUSTOMER_AGENT_URL || 'http://127.0.0.1:18002';
(async () => {
  assert.notEqual(new URL(base).port, '8002', 'Use an isolated release stack for public screenshots');
  const browser = await chromium.launch({ executablePath: process.env.BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; const checks = []; page.on('pageerror', e => errors.push(e.message));
  const out = 'docs/images'; fs.mkdirSync(out, { recursive: true });
  const screenshot = name => page.screenshot({ path: `${out}/${name}.png`, fullPage: false });
  const fresh = async () => { await page.goto(base + '/chat'); await page.getByLabel('消息', { exact: true }).waitFor(); };
  async function send(question, progress = false) {
    await page.getByLabel('消息', { exact: true }).fill(question);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await page.waitForURL(/\/chat\/[a-f0-9-]+$/);
    if (progress) {
      await page.getByRole('region', { name: '实时执行进度' }).waitFor({ timeout: 150000 });
      await screenshot('sse-progress');
    }
    await page.waitForFunction(() => !document.querySelector('.processing') && !!document.querySelector('.message.assistant'), undefined, { timeout: 150000 });
    const cid = page.url().split('/').at(-1);
    const r = await page.request.get(`${base}/api/v1/conversations/${cid}/workspace?tenant_id=default&user_id=u001`);
    assert.equal(r.status(), 200); return r.json();
  }
  try {
    const session = await (await page.request.get(base + '/api/v1/session')).json();
    assert.equal(session.development_mode, true);
    await fresh(); await screenshot('customer-chat');
    let w = await send('查订单202606040001，如果符合条件就申请退货退款');
    assert.equal(w.pending_actions.length, 0); assert.equal(w.tickets.length, 0);
    assert.ok(Object.values(w.responses).some(r => r.plan?.steps.some(s => s.status === 'not_satisfied')));
    await screenshot('scenario-shipped'); checks.push('Shipped fixture blocks refund, no action or ticket');
    await fresh(); w = await send('查订单202606040002，如果符合条件就申请退货退款');
    assert.equal(w.pending_actions.length, 0); assert.equal(w.tickets.length, 0);
    await screenshot('scenario-evidence'); checks.push('Delivered fixture without review evidence blocks refund');
    await fresh(); w = await send('查订单202606040003，如果符合条件就申请退货退款');
    assert.equal(w.pending_actions.length, 1); assert.equal(w.tickets.length, 0);
    const action = w.pending_actions[0];
    await screenshot('hitl-approval');
    await page.getByRole('button', { name: '确认提交', exact: true }).click();
    await page.getByText('已记录的服务工单', { exact: true }).waitFor({ timeout: 150000 });
    w = await (await page.request.get(`${base}/api/v1/conversations/${w.conversation.id}/workspace?tenant_id=default&user_id=u001`)).json();
    assert.equal(w.tickets.length, 1); await screenshot('scenario-approved');
    const duplicate = await page.request.post(`${base}/api/v1/confirmations/${action.id}/approve`, { data: { tenant_id: 'default', user_id: 'u001' } });
    assert.ok([200, 409].includes(duplicate.status()));
    const repeated = await (await page.request.get(`${base}/api/v1/conversations/${w.conversation.id}/workspace?tenant_id=default&user_id=u001`)).json();
    assert.equal(repeated.tickets.length, 1); checks.push('Approved fixture creates exactly one real demo MCP ticket, including repeated approval');
    await fresh(); w = await send('查订单202606040003，如果符合条件就申请退货退款');
    await page.getByRole('button', { name: '取消申请', exact: true }).click();
    await page.locator('.confirmation').waitFor({ state: 'hidden', timeout: 150000 });
    const rejected = await (await page.request.get(`${base}/api/v1/conversations/${w.conversation.id}/workspace?tenant_id=default&user_id=u001`)).json();
    assert.equal(rejected.tickets.length, 0); checks.push('Rejected request creates no ticket');
    await fresh(); await send('查询订单202606040001的物流进度', true); checks.push('Real SSE progress, model and MCP order query');
    await page.goto(base + '/operations'); await page.getByRole('heading', { name: '客服运营工作台' }).waitFor();
    await page.locator('.list-row').first().waitFor(); await screenshot('operations');
    await page.goto(base + '/demo'); await page.getByRole('heading', { name: '业务场景验证台' }).waitFor();
    await page.frameLocator('iframe').locator('#questionInput').waitFor(); await screenshot('demo-lab');
    checks.push('Customer, operations, Demo Lab, approval and three business outcome screenshots captured from real isolated application');
    assert.deepEqual(errors, []);
    fs.writeFileSync('data/release/browser.json', JSON.stringify({ status: 'passed', checks, page_errors: errors, source: 'isolated release demo with seeded fixtures only' }, null, 2));
    for (const check of checks) console.log('PASS:', check);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
