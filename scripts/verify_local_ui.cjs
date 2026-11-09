// Run after installing playwright under .local-tools/browser.
const { chromium } = require('../.local-tools/browser/node_modules/playwright');
const assert = require('node:assert/strict');
const baseUrl = new URL('/ops', process.env.CUSTOMER_AGENT_URL || 'http://127.0.0.1:8001/').toString();
const fullStack = process.env.CUSTOMER_AGENT_FULL === '1';

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const results = [];
  async function send(text) {
    await page.locator('#questionInput').fill(text);
    const response = page.waitForResponse(r => (r.url().endsWith('/api/v1/chat') || r.url().endsWith('/messages')) && r.request().method() === 'POST');
    await page.locator('#sendBtn').click();
    const r = await response;
    const payload = await r.json();
    assert.equal(r.status(), 200, JSON.stringify(payload));
    await page.locator('#sendBtn').waitFor({state: 'visible'});
    await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    return payload;
  }
  try {
    await page.goto(baseUrl);
    const first = await send('帮我查一下订单202606040001的物流单号');
    assert.ok(first.answer.includes('SF1234567890'));
    results.push('Order lookup');
    await page.getByRole('button', {name:'多轮追问', exact:false}).click();
    assert.equal(await page.locator('#conversationId').inputValue(), first.conversation_id);
    const follow = await send('是哪家快递公司？');
    assert.equal(follow.conversation_id, first.conversation_id);
    assert.ok(follow.answer.includes('顺丰'));
    assert.equal(await page.locator('#messages .msg').count(), 4);
    results.push('Multi-turn history and context');
    await page.locator('[data-mode="human"]').click();
    await page.locator('[data-mode="bot"]').click();
    assert.equal(await page.locator('#messages .msg').count(), 4);
    assert.equal(await page.locator('#conversationId').inputValue(), first.conversation_id);
    results.push('Bot/human workspace preserves chat');
    await page.getByRole('button', {name:'越权测试', exact:false}).click();
    assert.equal(await page.locator('#conversationId').inputValue(), '');
    const forbidden = await send('查询订单202606040001的物流单号');
    assert.ok(!forbidden.answer.includes('SF1234567890'));
    assert.ok(!forbidden.tool_results.some(t => t.payload?.found));
    results.push('Cross-user order isolation');
    await page.getByRole('button', {name:'多轮追问', exact:false}).click();
    assert.equal(await page.locator('#userId').inputValue(),'u002');
    assert.equal(await page.locator('#conversationId').inputValue(),forbidden.conversation_id);
    results.push('Follow-up preserves non-default identity');
    await page.getByRole('button', {name:'订单查询', exact:false}).click();
    assert.equal(await page.locator('#userId').inputValue(),'u001');
    assert.equal(await page.locator('#conversationId').inputValue(),'');
    await page.locator('#conversationId').fill('missing-conversation');
    const bad = page.waitForResponse(r => r.url().endsWith('/api/v1/chat'));
    await page.locator('#sendBtn').click();
    assert.equal((await bad).status(),404);
    await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    assert.equal(await page.locator('#conversationId').inputValue(),'');
    await send('你好');
    results.push('Stale conversation recovery');
    await page.locator('#newSessionBtn').click();
    const refund = await send('请为订单202606040003创建退款工单，原因是质量问题。请执行退款申请工具。');
    console.log('Refund reached confirmation:', Boolean(refund.pending_confirmation));
    if (refund.pending_confirmation) {
      const approval = page.waitForResponse(r => r.url().includes('/confirmations/') && r.url().endsWith('/approve'));
      await page.locator('#approveActionBtn').click();
      const approved = await approval;
      const data = await approved.json();
      assert.equal(approved.status(),200,JSON.stringify(data));
      await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
      assert.ok(JSON.stringify(data).includes('ticket_id'), JSON.stringify(data));
      assert.ok(!data.answer.includes('请确认是否继续提交'), 'Approval must show execution result');
      results.push('Refund confirmation executes ticket');
    } else {
      throw Error('Refund did not produce a confirmation');
    }
    await page.locator('#newSessionBtn').click();
    const cancelled = await send('请为订单202606040003创建退款工单，原因是商品损坏。请执行退款申请工具。');
    assert.ok(cancelled.pending_confirmation);
    const rejection = page.waitForResponse(r => r.url().endsWith('/reject'));
    await page.locator('#rejectActionBtn').click();
    assert.equal((await rejection).status(),200);
    await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    results.push('Refund cancellation');
    await page.locator('#newSessionBtn').click();
    const human = await send('我要投诉，这个问题必须人工处理，请调用转人工工具。');
    assert.ok(human.pending_confirmation, 'Handoff requires confirmation');
    const transfer = page.waitForResponse(r => r.url().endsWith('/approve'));
    await page.locator('#approveActionBtn').click();
    const tr = await transfer;
    assert.equal(tr.status(),200,await tr.text());
    await page.waitForFunction(() => !document.getElementById('sendBtn').disabled);
    await page.locator('[data-mode="human"]').click();
    await page.locator('.human-card').filter({hasText:human.conversation_id.slice(0,12)}).click();
    await page.locator('#assignHumanBtn').click();
    await page.locator('#resolutionSummary').waitFor();
    await send('您好，我已经为您核实，可以继续为您处理。');
    await page.locator('#resolutionSummary').fill('已解释处理流程，恢复智能客服。');
    await page.locator('#submitResolutionBtn').click();
    await page.locator('#confirmResolutionBtn').click();
    await page.waitForFunction(() => document.getElementById('evidenceBody').textContent.includes('已结束'));
    await page.locator('[data-mode="bot"]').click();
    const resumed = await send('你好，现在可以继续咨询了吗？');
    assert.equal(resumed.conversation_id,human.conversation_id);
    assert.equal(resumed.service_mode,'bot');
    results.push('Human handoff, reply, resolution and bot resume');
    assert.equal(await page.getByRole('button',{name:'售后政策',exact:false}).isDisabled(),!fullStack);
    await page.locator('#newSessionBtn').click();
    assert.equal(await page.locator('#conversationId').inputValue(),'');
    assert.equal(await page.locator('#messages .msg').count(),0);
    assert.equal(await page.locator('#metricTools').textContent(),'0');
    assert.equal(await page.locator('#confirmationCard').isVisible(),false);
    results.push('New session resets display; knowledge scenario matches runtime configuration');
    assert.deepEqual(errors,[]);
    console.log('PASS',JSON.stringify(results));
  } finally {
    await page.screenshot({path:fullStack ? 'data/ui-full-verification.png' : 'data/ui-verification.png',fullPage:true});
    await browser.close();
  }
})().catch(e => {console.error(e);process.exitCode=1;});

