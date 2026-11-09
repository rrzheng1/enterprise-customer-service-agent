const assert = require('node:assert/strict');
// Fetch the persisted response by the real streamed request ID. A canceled fetch reader
// can make CDP response bodies unavailable, so do not depend on response.text().
async function persistedStreamReply(response, page) {
  assert.equal(response.status(), 200);
  assert.ok(response.headers()['content-type'].includes('text/event-stream'));
  const body = response.request().postDataJSON();
  const deadline = Date.now() + 150000;
  while (Date.now() < deadline) {
    const r = await page.request.get(new URL(`/api/v1/conversations/${body.conversation_id}/workspace?tenant_id=default&user_id=u001`, response.url()).toString());
    assert.equal(r.status(), 200);
    const w = await r.json(); const run = w.runs.find(r => r.request_id === body.metadata.idempotency_key);
    assert.ok(!run || run.status !== 'failed', 'Actual stream run failed');
    const reply = run && w.responses[run.id];
    if (reply) { await page.locator('.processing').waitFor({ state: 'hidden', timeout: 150000 }); return reply; }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error('No persisted ChatResponse for the streamed request');
}
module.exports = { persistedStreamReply };
