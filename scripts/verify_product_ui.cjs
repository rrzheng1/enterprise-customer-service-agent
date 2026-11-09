// Real browser/business verification. Uses seeded fixtures, never changes order status.
const { chromium } = require('../.local-tools/browser/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { persistedStreamReply } = require('./sse_browser_helpers.cjs');
const base = process.env.CUSTOMER_AGENT_URL || 'http://127.0.0.1:8002';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const errors = []; const report = { checks: [], conversations: [], errors };
  page.on('pageerror', e => errors.push(e.message));
  const passed = name => { report.checks.push(name); console.log('PASS:', name); };
  async function send(question) {
    await page.getByLabel('消息', { exact: true }).fill(question);
    const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/chat/stream' && r.request().method() === 'POST', { timeout: 150000 });
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const r = await response; assert.equal(r.status(), 200);
    const data = await persistedStreamReply(r, page); report.conversations.push(data.conversation_id);
    await page.getByRole('button', { name: '新建会话', exact: true }).waitFor({ state: 'visible' });
    await page.waitForFunction(() => !document.querySelector('.new-chat').disabled);
    return data;
  }
  async function fresh() { await page.getByRole('button', { name: '新建会话', exact: true }).click(); await page.waitForURL('**/chat'); }
  async function decide(button, decision) {
    const [r] = await Promise.all([page.waitForResponse(r => r.url().includes('/confirmations/') && r.url().endsWith('/' + decision), { timeout: 150000 }), page.getByRole('button', { name: button, exact: true }).click()]);
    assert.equal(r.status(), 200, await r.text());
    await page.waitForFunction(() => !document.querySelector('.new-chat').disabled);
    return r.json();
  }
  try {
    await page.goto(base + '/chat'); await page.getByLabel('消息', { exact: true }).waitFor();
    passed('Customer workspace loads without debug fields');
    await page.screenshot({ path: 'data/product-chat-empty.png', fullPage: true });
    const first = await send('查询订单202606040001的物流进度');
    const follow = await send('它现在到哪里了？'); assert.equal(first.conversation_id, follow.conversation_id); assert.equal(first.thread_id, follow.thread_id);
    assert.ok(await page.locator('.message.user').count() >= 2);
    passed('Real order query and multi-turn preserve conversation/thread and history');
    const firstUrl = page.url(); await fresh(); const shipped = await send('查订单202606040001，如果符合条件就申请退货退款');
    assert.equal(shipped.pending_confirmation, null); assert.ok(shipped.plan.steps.some(s => s.status === 'not_satisfied'));
    assert.equal(await page.locator('.confirmation').count(), 0); passed('Shipped order blocks refund without confirmation');
    await fresh(); const evidence = await send('查订单202606040002，如果符合条件就申请退货退款');
    assert.equal(evidence.pending_confirmation, null); passed('Delivered order with missing review evidence blocks refund');
    await fresh(); const eligible = await send('查订单202606040003，如果符合条件就申请退货退款');
    assert.equal(eligible.pending_confirmation.tool_name, 'create_refund_case'); await page.getByRole('region', { name: '操作确认' }).waitFor();
    await page.reload(); await page.getByRole('button', { name: '确认提交', exact: true }).waitFor(); passed('Pending confirmation survives full page reload');
    const approved = await decide('确认提交', 'approve'); assert.equal(approved.status, 'executed');
    const business = await (await page.request.get(`${base}/api/v1/conversations/${eligible.conversation_id}/workspace?tenant_id=default&user_id=u001`)).json();
    assert.equal(business.tickets.length, 1); assert.ok(business.tickets[0].id);
    await page.getByText('已记录的服务工单', { exact: true }).waitFor();
    passed('Approval returns actual MCP ticket and persisted business result');
    await page.screenshot({ path: 'data/product-chat-ticket.png', fullPage: true });
    await fresh(); await send('查订单202606040003，如果符合条件就申请退货退款'); const rejected = await decide('取消申请', 'reject'); assert.equal(rejected.status, 'rejected');
    assert.equal(await page.locator('.ticket-results').count(), 0); passed('Reject cancels request without creating a ticket');
    await page.goto(firstUrl); await page.getByLabel('消息', { exact: true }).waitFor(); await page.waitForFunction(() => document.querySelectorAll('.message.user').length >= 2);
    passed('Switching conversations restores prior persisted messages');
    await page.getByRole('link', { name: '运营工作台', exact: true }).click(); await page.getByRole('heading', { name: '客服运营工作台' }).waitFor();
    await page.locator('.list-row').first().waitFor(); await page.locator('.list-row').first().click(); await page.locator('.transcript').waitFor();
    passed('Operations loads real conversations, transcript, queue and runs');
    await page.screenshot({ path: 'data/product-operations.png', fullPage: true });
    await page.getByRole('link', { name: '场景验证', exact: true }).click(); await page.getByRole('heading', { name: '业务场景验证台' }).waitFor();
    assert.equal((await page.request.get(base + '/ops')).status(), 200); assert.equal((await page.request.get(base + '/demo/legacy')).status(), 200);
    passed('Demo Lab and both legacy compatibility paths remain accessible');
    await page.setViewportSize({ width: 390, height: 844 }); await page.goto(base + '/chat'); await page.getByLabel('消息', { exact: true }).waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: 'data/product-mobile.png', fullPage: true }); passed('390px mobile layout has no horizontal overflow');
    assert.deepEqual(errors, []); report.status = 'passed';
  } catch (e) { report.status = 'failed'; report.error = e.message; await page.screenshot({ path: 'data/product-ui-failure.png', fullPage: true }); throw e; }
  finally { fs.writeFileSync('data/product-ui-validation.json', JSON.stringify(report, null, 2)); await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
