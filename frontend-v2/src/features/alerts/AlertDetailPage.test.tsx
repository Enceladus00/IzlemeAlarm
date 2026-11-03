import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { alertDetail, alertsHandler, queueAlerts, sampleTransaction } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const ahmet = queueAlerts.find((alert) => alert.alert_id === 5518)!;
let patches: unknown[] = [];

beforeEach(() => {
  patches = [];
  server.use(
    alertsHandler(),
    http.get(`${API}/alerts/5518`, () =>
      HttpResponse.json(
        alertDetail(ahmet, {
          history: [
            { old_status: null, new_status: 'new', note: null, changed_at: ahmet.created_at },
            { old_status: 'new', new_status: 'in_review', note: 'Müşteriyle görüşülecek.', changed_at: '2026-10-27T09:00:00' },
          ],
        }),
      ),
    ),
    http.get(`${API}/alerts/404404`, () => HttpResponse.json({ detail: 'Alert not found.' }, { status: 404 })),
    http.patch(`${API}/alerts/5518/status`, async ({ request }) => {
      const body = (await request.json()) as { status: string; note: string | null };
      patches.push(body);
      return HttpResponse.json({ alert_id: 5518, status: body.status, changed: body.status !== 'new' });
    }),
    http.get(`${API}/alerts/5518/customer-transactions`, () =>
      HttpResponse.json({ customer_no: 'C-1042', customer_name: 'Ahmet Yılmaz', items: [sampleTransaction] }),
    ),
  );
});

describe('Alert detail', () => {
  it('shows the alert, its transactions, history and the customer’s other alerts', async () => {
    storeSession('admin');
    renderApp('/alerts/5518');

    expect(await screen.findByRole('heading', { name: 'Alarm #5518 · R03 Ortalamadan sapma' })).toBeInTheDocument();
    const linked = screen.getByRole('table', { name: 'Alarma bağlı işlemler' });
    expect(within(linked).getByText('45.000,00 TRY')).toBeInTheDocument();
    expect(within(linked).getByLabelText('Giden')).toBeInTheDocument();

    expect(screen.getByText('Yeni → İncelemede')).toBeInTheDocument();
    expect(screen.getByText('Müşteriyle görüşülecek.')).toBeInTheDocument();
    expect(screen.getAllByText('İşlemi yapan', { exact: false })[0]!.querySelector('[data-placeholder]')).not.toBeNull();

    expect(await screen.findByText('3 alarm')).toBeInTheDocument();
    const current = screen.getAllByRole('link', { current: 'page' }).map((link) => link.getAttribute('href'));
    expect(current).toContain('/alerts/5518');
  });

  it('requires a note before closing, then saves the decision', async () => {
    storeSession('admin');
    const { user } = renderApp('/alerts/5518');
    await screen.findByRole('heading', { name: /Alarm #5518/ });

    await user.selectOptions(screen.getByLabelText('Yeni durum'), 'closed');
    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));
    expect(await screen.findByText('Alarmı kapatmak veya şüpheli olarak onaylamak için not zorunludur.')).toBeInTheDocument();
    expect(patches).toHaveLength(0);

    await user.type(screen.getByLabelText(/Analist gerekçesi/), '  Gelir belgesi doğrulandı.  ');
    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));
    expect(await screen.findByText('Alarm durumu ve analist notu kaydedildi.')).toBeInTheDocument();
    expect(patches).toEqual([{ status: 'closed', note: 'Gelir belgesi doğrulandı.' }]);
  });

  it('reports a no-op save', async () => {
    storeSession('admin');
    const { user } = renderApp('/alerts/5518');
    await screen.findByRole('heading', { name: /Alarm #5518/ });
    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));
    expect(await screen.findByText('Değişiklik yok: durum aynı ve not girilmedi.')).toBeInTheDocument();
    expect(patches).toEqual([{ status: 'new', note: null }]);
  });

  it('shows server validation errors', async () => {
    server.use(
      http.patch(`${API}/alerts/5518/status`, () =>
        HttpResponse.json({ detail: 'A note is required to close or confirm an alert.' }, { status: 422 }),
      ),
    );
    storeSession('admin');
    const { user } = renderApp('/alerts/5518');
    await screen.findByRole('heading', { name: /Alarm #5518/ });
    await user.selectOptions(screen.getByLabelText('Yeni durum'), 'in_review');
    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));
    expect(await screen.findByText('A note is required to close or confirm an alert.')).toBeInTheDocument();
  });

  it('is read-only without alert:update and hides the analysis link without customer:view', async () => {
    storeSession('reviewer');
    renderApp('/alerts/5518');
    expect(await screen.findByText('Hesabınız alarmları inceleyebilir ancak durumlarını değiştiremez.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Kararı kaydet' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /İşlem analizinde aç/ })).not.toBeInTheDocument();
  });

  it('loads the alert-scoped customer history on demand', async () => {
    storeSession('reviewer');
    const { user } = renderApp('/alerts/5518');
    await user.click(await screen.findByRole('button', { name: 'Müşteri işlem geçmişini yükle' }));
    const table = await screen.findByRole('table', { name: 'Müşteri işlem geçmişi' });
    expect(within(table).getByText('TX-0091')).toBeInTheDocument();
  });

  it('shows a not-found state', async () => {
    storeSession('admin');
    renderApp('/alerts/404404');
    expect(await screen.findByText('Alarm bulunamadı')).toBeInTheDocument();
  });

  it('returns to the queue with its filters', async () => {
    storeSession('admin');
    const { user, router } = renderApp('/alerts?severity=high');
    await user.click(await screen.findByRole('button', { name: 'Ahmet Yılmaz için incelemeye başla' }));
    await user.click(await screen.findByRole('link', { name: 'Alarm kuyruğuna dön' }));
    await waitFor(() => expect(router.state.location.search).toBe('?severity=high'));
  });
});
