// Real HTTP SSE + browser + MCP. No intercepted success responses or changed order facts.
const { chromium } = require('../.local-tools/browser/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.CUSTOMER_AGENT_URL || 'http://127.0.0.1:8002';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  let posts = 0; const errors = []; const checks = [];
  context.on('request', r => { if (r.method() === 'POST' && new URL(r.url()).pathname === '/api/v1/chat/stream') posts++; });
  context.on('page', p => p.on('pageerror', e => errors.push(e.message)));
  await context.addInitScript(() => {
    window.__liveNodeSeen = false; window.__drafts = [];
    new MutationObserver(() => {
      if (document.querySelector('.stream-progress') && document.querySelector('.processing')) window.__liveNodeSeen = true;
      const draft = document.querySelector('[data-testid="streaming-answer"] .markdown')?.textContent;
      if (draft && !window.__drafts.includes(draft)) window.__drafts.push(draft);
    }).observe(document, { childList: true, subtree: true, characterData: true });
  });
  let page = await context.newPage();
  const passed = s => { checks.push(s); console.log('PASS:', s); };
  const fresh = async () => { await page.goto(base + '/chat'); await page.getByLabel('消息', { exact: true }).waitFor(); };
  async function begin(question) {
    await page.getByLabel('消息', { exact: true }).fill(question);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await page.waitForURL(/\/chat\/[a-f0-9-]+$/);
    await page.getByRole('region', { name: '实时执行进度' }).waitFor({ timeout: 150000 });
    return page.url().split('/').at(-1);
  }
  async function settled() { await page.waitForFunction(() => !document.querySelector('.processing') && !!document.querySelector('.message.assistant'), undefined, { timeout: 150000 }); }
  async function restored(cid) { await page.goto(base + '/chat/' + cid); await settled(); }
  try {
    await fresh(); let cid = await begin('查询订单202606040001的物流进度'); await settled();
    assert.ok(await page.evaluate(() => window.__liveNodeSeen));
    assert.ok(await page.evaluate(() => window.__drafts.length > 1));
    assert.equal(await page.locator('.message.assistant').count(), 1);
    assert.equal(await page.locator('[data-testid="streaming-answer"]').count(), 0);
    passed('Live node progress and native incremental answer render before persistence, one final answer');
    await page.screenshot({ path: 'data/stream-chat.png', fullPage: true });
    await fresh(); cid = await begin('查询订单202606040001的物流进度'); const stoppedPosts = posts;
    await page.getByRole('button', { name: '停止接收', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 1 && !document.querySelector('textarea[aria-label="消息"]').disabled, undefined, { timeout: 150000 });
    assert.equal(posts, stoppedPosts); passed('Stop receiving aborts transport; GET recovery restores result without another POST');
    await fresh(); cid = await begin('查询订单202606040001的物流进度'); const refreshPosts = posts;
    await page.reload(); await settled();
    assert.equal(posts, refreshPosts); assert.equal(await page.locator('.message.assistant').count(), 1);
    passed('Refresh during an active run recovers persisted result without resubmission');
    await fresh(); cid = await begin('查询订单202606040001的物流进度'); const switchPosts = posts;
    await page.getByRole('button', { name: '新建会话', exact: true }).click(); await page.waitForURL('**/chat');
    assert.equal(await page.locator('.message.assistant').count(), 0);
    await restored(cid); assert.equal(posts, switchPosts); passed('Switching away detaches the stream and returning restores only the owned conversation');
    await fresh(); cid = await begin('查询订单202606040001的物流进度'); const closePosts = posts;
    await page.close(); page = await context.newPage(); await restored(cid);
    assert.equal(posts, closePosts); passed('Closing a browser tab leaves a single server run; a new tab recovers the saved answer');
    await fresh(); cid = await begin('查订单202606040003，如果符合条件就申请退货退款'); await settled();
    await page.getByRole('button', { name: '确认提交', exact: true }).waitFor();
    await page.reload(); await page.getByRole('button', { name: '确认提交', exact: true }).waitFor();
    await page.getByRole('button', { name: '确认提交', exact: true }).click();
    await page.getByText('已记录的服务工单', { exact: true }).waitFor({ timeout: 150000 });
    assert.equal(await page.locator('.confirmation').count(), 0);
    passed('Streamed approval card reloads from persisted state and creates a real MCP ticket via original approval API');
    await fresh(); await begin('查订单202606040003，如果符合条件就申请退货退款'); await settled();
    await page.getByRole('button', { name: '取消申请', exact: true }).click(); await page.locator('.confirmation').waitFor({ state: 'hidden', timeout: 150000 });
    assert.equal(await page.locator('.ticket-results').count(), 0); passed('Streamed confirmation rejection creates no ticket');
    assert.deepEqual(errors, []); fs.writeFileSync('data/stream-ui-validation.json', JSON.stringify({ status: 'passed', checks, errors, streaming_posts: posts }, null, 2));
  } catch (e) { await page.screenshot({ path: 'data/stream-ui-failure.png', fullPage: true }).catch(() => {}); fs.writeFileSync('data/stream-ui-validation.json', JSON.stringify({ status: 'failed', checks, errors, error: e.message }, null, 2)); throw e; }
  finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
