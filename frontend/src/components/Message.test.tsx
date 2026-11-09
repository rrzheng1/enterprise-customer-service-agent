import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ConfirmationCard, Message } from './Message';
import type { Action } from '../api/client';
describe('Business interaction presentation', () => {
  it('renders material action fields and disables expired approvals', () => {
    const a: Action = { id: 'a', tenant_id: 'default', user_id: 'u001', action_type: 'refund', tool_name: 'create_refund_case', status: 'pending', risk_level: 'high', confirmation_prompt: '确认申请', expired: true, arguments: { order_id: '202606040003', reason: '商品故障' } };
    const html = renderToStaticMarkup(<ConfirmationCard action={a} busy={false} onDecision={() => {}}/>);
    expect(html).toContain('202606040003'); expect(html).toContain('商品故障');
    expect(html).toContain('disabled=""'); expect(html).toContain('确认已过期');
    expect(html).not.toContain('申请成功');
  });
  it('never renders untrusted HTML in customer messages', () => {
    const html = renderToStaticMarkup(<Message message={{ id: 'm', role: 'assistant', content: '<script>alert(1)</script> **答复**' }}/>);
    expect(html).not.toContain('<script>');
  });
});
