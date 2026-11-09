const { chromium } = require('../.local-tools/browser/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const context = await browser.newContext(); const page = await context.newPage(); let posts = 0; const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/api/v1/chat/stream')) posts++; });
  try {
    await page.goto((process.env.CUSTOMER_AGENT_URL || 'http://127.0.0.1:8002') + '/chat');
    await page.getByLabel('消息', { exact: true }).fill('查询订单202606040001的物流进度');
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await page.getByRole('region', { name: '实时执行进度' }).waitFor({ timeout: 150000 });
    await context.setOffline(true); await page.getByRole('alert').waitFor();
    await page.screenshot({ path: 'data/stream-network-offline.png', fullPage: true });
    await context.setOffline(false);
    await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 1 && !document.querySelector('textarea[aria-label="消息"]').disabled, undefined, { timeout: 150000 });
    assert.equal(posts, 1); assert.deepEqual(errors, []);
    fs.writeFileSync('data/stream-network-validation.json', JSON.stringify({ status: 'passed', streaming_posts: posts, errors, check: 'Actual browser offline/online recovers persisted answer via GET, never re-POSTs' }, null, 2));
    console.log('PASS: actual browser offline/online recovery; one streaming POST and one saved answer');
  } finally { await context.setOffline(false); await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
