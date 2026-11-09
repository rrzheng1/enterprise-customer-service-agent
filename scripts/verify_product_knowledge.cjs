const { chromium } = require('../.local-tools/browser/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { persistedStreamReply } = require('./sse_browser_helpers.cjs');
(async () => {
  const base = process.env.CUSTOMER_AGENT_URL || 'http://127.0.0.1:5173';
  const browser = await chromium.launch({ executablePath: process.env.BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = []; const checks = []; page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto(base + '/chat'); const input = page.getByLabel('消息', { exact: true }); await input.waitFor();
    await input.fill('银行卡退款一般几天到账？'); await input.press('Shift+Enter');
    assert.ok((await input.inputValue()).endsWith('\n')); checks.push('Shift+Enter inserts newline');
    const [r] = await Promise.all([page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/chat/stream' && r.request().method() === 'POST', { timeout: 150000 }), input.press('Enter')]);
    assert.equal(r.status(), 200); const reply = await persistedStreamReply(r, page); assert.ok(reply.knowledge.length);
    await page.locator('.sources summary').last().waitFor(); await page.locator('.sources summary').last().click();
    assert.ok((await page.locator('.sources').last().innerText()).includes('退款')); checks.push('Real RAG request and expandable source through Vite Proxy');
    const url = page.url(); await page.screenshot({ path: 'data/product-knowledge.png', fullPage: true });
    await page.waitForFunction(() => !document.querySelector('.new-chat').disabled);
    await page.locator('.conversation:not(.active)').first().click(); await page.waitForURL(u => u.toString() !== url); checks.push('Sidebar switches conversation route');
    await page.goto(url); await page.locator('.sources summary').last().waitFor(); checks.push('Knowledge sources restored after reload');
    await page.goto(base + '/chat/not-an-owned-conversation'); await page.getByRole('alert').waitFor(); checks.push('Invalid conversation displays real backend error');
    assert.deepEqual(errors, []); fs.writeFileSync('data/product-knowledge-validation.json', JSON.stringify({ status: 'passed', checks, errors, sources: reply.knowledge.map(k => k.source) }, null, 2));
    for (const check of checks) console.log('PASS:', check);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
