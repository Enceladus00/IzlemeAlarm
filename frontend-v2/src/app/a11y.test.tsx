import { screen } from '@testing-library/react';
import axe from 'axe-core';
import { http, HttpResponse } from 'msw';
import { alertDetail, alertsHandler, queueAlerts, sampleTransaction } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { ruleFixtures } from '@/test/ruleData';
import { API, server } from '@/test/server';

/**
 * Automated WCAG checks (axe-core) on every screen. jsdom cannot compute
 * colours, so contrast is checked separately (palette validator, manual review).
 */
async function expectNoViolations() {
  const results = await axe.run(document.body, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    rules: { 'color-contrast': { enabled: false } },
  });
  const summary = results.violations.map(
    (violation) => `${violation.id}: ${violation.help} → ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`,
  );
  expect(summary).toEqual([]);
}

beforeEach(() => {
  server.use(
    alertsHandler(),
    http.get(`${API}/alerts/rule-codes`, () => HttpResponse.json(['R01', 'R02', 'R03'])),
    http.get(`${API}/alerts/5518`, () => HttpResponse.json(alertDetail(queueAlerts[0]!))),
    http.get(`${API}/transactions`, () => HttpResponse.json({ total: 1, items: [{ ...sampleTransaction, alert_linked: true }] })),
    http.get(`${API}/rules`, () => HttpResponse.json(ruleFixtures)),
    http.get(`${API}/demo/status`, () =>
      HttpResponse.json({ seeded: false, fixture_ready: false, customers: 0, accounts: 0, transactions: 0, customer_rows: [], account_rows: [], transaction_rows: [], scenarios: [], seed_enabled: true }),
    ),
    http.get(`${API}/users`, () => HttpResponse.json([{ user_id: 1, username: 'admin', role_code: 'admin', is_active: true, created_at: null }])),
    http.get(`${API}/users/roles`, () => HttpResponse.json([{ role_code: 'admin', name: 'Admin' }])),
    http.get(`${API}/audit-log`, () =>
      HttpResponse.json({ total: 1, items: [{ audit_id: 1, actor_id: 1, action: 'LOGIN_SUCCESS', entity_type: 'auth', entity_id: '1', details: { username: 'admin' }, created_at: '2026-11-03T10:00:00' }] }),
    ),
  );
});

describe('accessibility (axe-core, WCAG 2.1 A/AA)', () => {
  it('login page', async () => {
    renderApp('/login');
    await screen.findByRole('heading', { name: 'Sentinel oturum açma' });
    await expectNoViolations();
  });

  it.each([
    ['/overview', 'Tespit özeti'],
    ['/system', 'Sistem özeti'],
    ['/alerts', 'Alarm kuyruğu'],
    ['/alerts/5518', /Alarm #5518/],
    ['/transactions', 'İşlem analizi'],
    ['/data', 'Veri yönetimi'],
    ['/demo', 'Demo laboratuvarı'],
    ['/rules?rule=R01', 'Kural yönetimi'],
    ['/users', 'Kullanıcı yönetimi'],
    ['/audit', 'Denetim kaydı'],
  ] as const)('%s', async (path, heading) => {
    storeSession('admin');
    renderApp(path);
    await screen.findByRole('heading', { level: 1, name: heading });
    // Let data-dependent sections render before auditing.
    await new Promise((resolve) => setTimeout(resolve, 300));
    await expectNoViolations();
  }, 15_000);
});
