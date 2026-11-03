import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { AuditEvent } from '@/api/schemas/users';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const events: AuditEvent[] = Array.from({ length: 120 }, (_, index) => ({
  audit_id: 120 - index,
  actor_id: index % 3 === 0 ? null : 1,
  action: ['LOGIN_SUCCESS', 'LOGIN_FAILED', 'ACCESS_DENIED', 'RULE_UPDATED'][index % 4]!,
  entity_type: 'auth',
  entity_id: index % 2 ? String(index) : null,
  details: index % 4 === 2 ? { username: 'ayse', permission: 'user:manage' } : {},
  created_at: '2026-11-03T12:12:02.106380',
}));

const requests: URLSearchParams[] = [];

beforeEach(() => {
  requests.length = 0;
  server.use(
    http.get(`${API}/audit-log`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests.push(params);
      const offset = Number(params.get('offset'));
      const limit = Number(params.get('limit'));
      return HttpResponse.json({ total: events.length, items: events.slice(offset, offset + limit) });
    }),
    http.get(`${API}/users`, () =>
      HttpResponse.json([{ user_id: 1, username: 'admin', role_code: 'admin', is_active: true, created_at: null }]),
    ),
  );
});

describe('Audit log', () => {
  it('pages through events on the server', async () => {
    storeSession('admin');
    const { user, router } = renderApp('/audit');
    expect(await screen.findByText('120 olay · 1–50 gösteriliyor')).toBeInTheDocument();
    expect(requests[0]!.get('offset')).toBe('0');
    expect(requests[0]!.get('limit')).toBe('50');

    await user.click(screen.getByRole('button', { name: 'Sonraki' }));
    expect(await screen.findByText('120 olay · 51–100 gösteriliyor')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?page=2');
    expect(requests.at(-1)!.get('offset')).toBe('50');

    await user.selectOptions(screen.getByLabelText('Sayfa başına'), '200');
    expect(await screen.findByText('120 olay · 1–120 gösteriliyor')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sonraki' })).toBeDisabled();
  });

  it('labels actions, resolves actor names and expands details', async () => {
    storeSession('admin');
    const { user } = renderApp('/audit');
    const table = await screen.findByRole('table', { name: 'Denetim kaydı' });
    expect(within(table).getAllByText('Yetkisiz erişim denemesi').length).toBeGreaterThan(0);
    expect(within(table).getAllByText('RULE_UPDATED').length).toBeGreaterThan(0);
    expect(within(table).getAllByText('Sistem').length).toBeGreaterThan(0);
    expect(within(table).getAllByText('admin').length).toBeGreaterThan(0);

    const toggle = within(table).getAllByRole('button', { name: 'Ayrıntıları göster' })[0]!;
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById(toggle.getAttribute('aria-controls')!)).toHaveTextContent('"permission": "user:manage"');
  });

  it('shows actor ids without user:manage', async () => {
    server.use(http.get(`${API}/auth/me`, () => HttpResponse.json({ username: 'auditor', role_code: 'auditor', permissions: ['audit:view'] })));
    storeSession('admin');
    renderApp('/audit');
    const table = await screen.findByRole('table', { name: 'Denetim kaydı' });
    await waitFor(() => expect(within(table).getAllByText('Kullanıcı #1').length).toBeGreaterThan(0));
  });

  it('shows an empty log', async () => {
    server.use(http.get(`${API}/audit-log`, () => HttpResponse.json({ total: 0, items: [] })));
    storeSession('admin');
    renderApp('/audit');
    expect(await screen.findByText('Henüz denetim olayı kaydedilmedi.')).toBeInTheDocument();
  });
});
