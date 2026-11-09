import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { AuditEvent } from '@/api/schemas/users';
import { alertDetail, daysAgo, historyEvent, makeAlert } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const events: AuditEvent[] = Array.from({ length: 120 }, (_, index) => ({
  audit_id: 120 - index,
  actor_id: index % 3 === 0 ? null : 1,
  actor_name: index % 3 === 0 ? null : 'admin',
  actor_role: index % 3 === 0 ? null : 'admin',
  action: ['LOGIN_SUCCESS', 'LOGIN_FAILED', 'ACCESS_DENIED', 'RULE_UPDATED'][index % 4]!,
  entity_type: 'auth',
  entity_id: index % 2 ? String(index) : null,
  details: index % 4 === 2 ? { username: 'ayse', permission: 'user:manage' } : {},
  created_at: '2026-11-03T12:12:02.106380',
  grouped: [],
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

  it('takes actor names from the API, so it works without user:manage', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/audit');
    const table = await screen.findByRole('table', { name: 'Denetim kaydı' });
    await waitFor(() => expect(within(table).getAllByText('admin').length).toBeGreaterThan(0));
  });

  it('hides customer views by default and filters on the server (K6)', async () => {
    storeSession('admin');
    const { user, router } = renderApp('/audit');
    await screen.findByRole('table', { name: 'Denetim kaydı' });
    const first = requests[0]!;
    expect(first.get('exclude_action')).toBe('customer.viewed');
    expect(first.get('action')).toBeNull();
    expect(first.get('date_from')).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    await user.selectOptions(screen.getByLabelText('Olay türü'), 'customer.viewed');
    await waitFor(() => expect(requests.at(-1)!.get('action')).toBe('customer.viewed'));
    expect(requests.at(-1)!.get('exclude_action')).toBeNull();
    expect(router.state.location.search).toBe('?type=customer.viewed');

    await user.selectOptions(screen.getByLabelText('İşlemi yapan'), '1');
    await waitFor(() => expect(requests.at(-1)!.get('actor_id')).toBe('1'));
    await user.type(screen.getByLabelText('Kayıt'), 'C-1042{Enter}');
    await waitFor(() => expect(requests.at(-1)!.get('entity_id')).toBe('C-1042'));
  });

  it('shows a detection run\'s R17 raises as one expandable row', async () => {
    const raise = (id: number, old: string, next: string) => ({
      audit_id: id,
      entity_id: String(id + 800),
      details: { rule: 'R17', K: 2, old, new: next, run_id: 'run-1' },
    });
    server.use(
      http.get(`${API}/audit-log`, () =>
        HttpResponse.json({
          total: 1,
          items: [
            {
              audit_id: 2,
              actor_id: null,
              actor_name: null,
              actor_role: null,
              action: 'alert.severity_raised',
              entity_type: 'alert',
              entity_id: '802',
              details: { rule: 'R17', K: 2, old: 'medium', new: 'high', run_id: 'run-1' },
              created_at: '2026-11-06T11:27:00',
              grouped: [raise(1, 'low', 'medium'), raise(2, 'medium', 'high')],
            },
          ],
        }),
      ),
    );
    storeSession('admin');
    const { user } = renderApp('/audit');
    const table = await screen.findByRole('table', { name: 'Denetim kaydı' });
    expect(within(table).getAllByText('Alarm önemi yükseltildi (R17)')).toHaveLength(1);
    expect(within(table).getByText(/2 alarm/)).toBeInTheDocument();

    await user.click(within(table).getByRole('button', { name: 'Ayrıntıları göster' }));
    expect(within(table).getByRole('link', { name: 'alert · 801' })).toHaveAttribute('href', '/alerts/801');
    expect(within(table).getByRole('link', { name: 'alert · 802' })).toBeInTheDocument();
    expect(within(table).getByText(/Düşük → Orta/)).toBeInTheDocument();
    expect(within(table).queryByRole('region', { name: 'Bu kararın izi' })).not.toBeInTheDocument();
  });

  it('shows an empty log', async () => {
    server.use(http.get(`${API}/audit-log`, () => HttpResponse.json({ total: 0, items: [] })));
    storeSession('admin');
    renderApp('/audit');
    expect(await screen.findByText('Henüz denetim olayı kaydedilmedi.')).toBeInTheDocument();
  });
});

describe('Audit log · decision trail (E06)', () => {
  it('traces an alert decision from the engine through two different people', async () => {
    const alert = makeAlert({ alert_id: 7001, customer_no: 'C-1042', customer_name: 'Ahmet Yılmaz', rule_code: 'R05', status: 'confirmed_suspicious', created_at: daysAgo(3) });
    server.use(
      http.get(`${API}/audit-log`, () =>
        HttpResponse.json({
          total: 2,
          items: [
            {
              audit_id: 2,
              actor_id: 9,
              actor_name: 'mehmet.ozturk',
              actor_role: 'compliance',
              action: 'alert.status_changed',
              entity_type: 'alert',
              entity_id: '7001',
              details: { old_status: 'in_review', new_status: 'confirmed_suspicious' },
              created_at: daysAgo(1),
            },
            {
              audit_id: 1,
              actor_id: 1,
              actor_name: 'ayse.karaca',
              actor_role: 'analyst',
              action: 'ACCESS_DENIED',
              entity_type: 'alert',
              entity_id: '7001',
              details: { permission: 'alert:confirm' },
              created_at: daysAgo(2),
            },
          ],
        }),
      ),
      http.get(`${API}/alerts/7001`, () =>
        HttpResponse.json(
          alertDetail(alert, {
            history: [
              historyEvent({ new_status: 'new', changed_at: daysAgo(3), changed_by: 0, actor_name: null, actor_role: null }),
              historyEvent({ old_status: 'new', new_status: 'in_review', changed_at: daysAgo(2), changed_by: 1, actor_name: 'ayse.karaca', actor_role: 'analyst' }),
              historyEvent({ old_status: 'in_review', new_status: 'confirmed_suspicious', changed_at: daysAgo(1), changed_by: 9, actor_name: 'mehmet.ozturk', actor_role: 'compliance' }),
            ],
          }),
        ),
      ),
    );
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/audit');
    const table = await screen.findByRole('table', { name: 'Denetim kaydı' });

    // The unauthorised attempt is a red row.
    expect(within(table).getByText('Yetkisiz erişim denemesi').closest('tr')).toHaveClass('bg-danger-soft');

    const decisionRow = within(table).getByText('Alarm kararı').closest('tr')!;
    await user.click(within(decisionRow).getByRole('button', { name: 'Ayrıntıları göster' }));
    const trail = await screen.findByRole('region', { name: 'Bu kararın izi' });
    expect(within(trail).getByText('Kural motoru alarm üretti (R05)')).toBeInTheDocument();
    expect(within(trail).getByText('Yeni → Uyum onayında')).toBeInTheDocument();
    expect(within(trail).getByText(/ayse\.karaca · Analist/)).toBeInTheDocument();
    expect(within(trail).getByText(/mehmet\.ozturk · Uyum Görevlisi/)).toBeInTheDocument();
    expect(within(trail).getByText(/dört göz kuralı sağlandı/)).toBeInTheDocument();
  });
});
