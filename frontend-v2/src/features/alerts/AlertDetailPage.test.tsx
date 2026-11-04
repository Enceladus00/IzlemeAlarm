import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { Explanation } from '@/api/schemas/alerts';
import {
  alertDetail,
  alertsHandler,
  customerContext,
  daysAgo,
  historyEvent,
  queueAlerts,
} from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const ahmet = queueAlerts.find((alert) => alert.alert_id === 5518)!;
const escalated = queueAlerts.find((alert) => alert.alert_id === 5590)!;
let decisions: unknown[] = [];
let contextCalls = 0;

const explanation: Explanation = {
  rule_code: 'R05',
  rule_name: 'Olağandışı tutar',
  alert_mode: 'ALERT',
  customer_type: 'BIREYSEL',
  parameter_status: 'PROVISIONAL',
  raw_x: '5.412300',
  score: '0.8127',
  x_esik: '4',
  x_kesin: '6',
  parameters: { x_esik: '4', x_kesin: '6' },
  steps: [
    { step: 1, text: 'Geçmiş işlemleri topla', status: 'completed', details: { history_count: 64 } },
    { step: 4, text: 'Skorla', status: 'completed', details: { maximum_z: '5.4123', score: '0.8127' } },
  ],
  run: { run_id: 'r-1', as_of: '2026-11-03T02:00:00' },
};

beforeEach(() => {
  decisions = [];
  contextCalls = 0;
  server.use(
    ...alertsHandler(),
    http.get(`${API}/alerts/5518`, () =>
      HttpResponse.json(
        alertDetail(ahmet, {
          explanation: { ...explanation, rule_code: 'R03' },
          history: [historyEvent({ new_status: 'new', changed_at: ahmet.created_at })],
        }),
      ),
    ),
    http.get(`${API}/alerts/5590`, () =>
      HttpResponse.json(
        alertDetail(escalated, {
          explanation,
          history: [
            historyEvent({ old_status: 'new', new_status: 'in_review', note: 'Profil dışı', changed_at: daysAgo(1) }),
          ],
          escalated_by: { user_id: 1, actor_name: 'ayse.karaca', changed_at: daysAgo(1) },
          events: [{ action: 'alert.rescored', created_at: daysAgo(0), details: { old_score: '0.7000', new_score: '0.8127' } }],
        }),
      ),
    ),
    http.get(`${API}/alerts/404404`, () => HttpResponse.json({ detail: 'Alert not found.' }, { status: 404 })),
    http.post(`${API}/alerts/decisions`, async ({ request }) => {
      const body = (await request.json()) as { alert_ids: number[]; status: string; note: string };
      decisions.push(body);
      return HttpResponse.json({ decision_id: 'd-1', status: body.status, alert_ids: body.alert_ids, decided_at: daysAgo(0) });
    }),
    http.get(`${API}/alerts/5518/customer-context`, () => {
      contextCalls += 1;
      return HttpResponse.json(customerContext);
    }),
  );
});

describe('Alert detail', () => {
  it('shows masked transactions, the explanation and the history with actors', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts/5518');

    expect(await screen.findByRole('heading', { name: 'Alarm #5518 · R03 Ortalamadan sapma' })).toBeInTheDocument();
    const linked = screen.getByRole('table', { name: 'Alarma bağlı işlemler' });
    expect(within(linked).getByText('Kaya T. L. Ş.')).toBeInTheDocument();
    expect(within(linked).getByText('…0311')).toBeInTheDocument();
    expect(within(linked).queryByText('Kaya Tekstil Ltd. Şti.')).not.toBeInTheDocument();

    expect(screen.getByText('Neden tetiklendi?')).toBeInTheDocument();
    expect(screen.getByText('Bu alarm geçici (onaylanmamış) parametrelerle üretildi.')).toBeInTheDocument();
    expect(screen.getByText(/İşlemi yapan: ayse\.karaca \(Analist\)/)).toBeInTheDocument();
    expect(await screen.findByText('3 alarm')).toBeInTheDocument();
  });

  it('fills the rule summary sentence from the stored calculation', async () => {
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/alerts/5590');
    expect(
      await screen.findByText('Bugünkü bir işlem, müşterinin olağan tutarından 5,41 kat “normal oynama” uzakta.'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Kural adımları (2)' }));
    expect(screen.getByText('4. Skorla')).toBeInTheDocument();
    expect(screen.getByText('Skor güncellendi: 0,7 → 0,8127')).toBeInTheDocument();
  });

  it('explains legacy alerts without a calculation', async () => {
    server.use(http.get(`${API}/alerts/5518`, () => HttpResponse.json(alertDetail(ahmet))));
    storeSession('ayse.karaca');
    renderApp('/alerts/5518');
    expect(await screen.findByText('Bu alarm eski bir kuraldan geldiği için hesap ayrıntısı yok.')).toBeInTheDocument();
  });

  it('offers analysts close/escalate and sends one atomic decision for the selected alerts', async () => {
    storeSession('ayse.karaca');
    const { user, router } = renderApp('/alerts/5518');
    await screen.findByRole('heading', { name: /Alarm #5518/ });
    expect(screen.getByRole('radio', { name: 'Kapat · yanlış alarm' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Şüpheli olarak onayla' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));
    expect(await screen.findByText('Bir karar seçin.')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Uyum görevlisine yükselt' }));
    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));
    expect(await screen.findByText('Not zorunlu.')).toBeInTheDocument();
    expect(decisions).toHaveLength(0);

    // all three of the customer's new alerts start selected; untick one
    await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(3));
    await user.click(screen.getByRole('checkbox', { name: /#5531/ }));
    await user.type(screen.getByLabelText(/Gerekçe/), '  Profil dışı giden işlem.  ');
    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/alerts'));
    expect(decisions).toEqual([{ alert_ids: [5518, 5524], status: 'in_review', note: 'Profil dışı giden işlem.' }]);
    expect(await screen.findByText('2 alarm uyum görevlisine gönderildi.')).toBeInTheDocument();
  });

  it('shows the four-eyes rule and names the failing alert', async () => {
    server.use(
      http.post(`${API}/alerts/decisions`, () =>
        HttpResponse.json(
          { detail: 'The user who escalated this alert cannot decide on it.', alert_id: 5590 },
          { status: 403 },
        ),
      ),
    );
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/alerts/5590');
    expect(await screen.findByText(/Yükselten: ayse\.karaca/)).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Kapat · açıklaması var' }));
    await user.type(screen.getByLabelText(/Gerekçe/), 'Açıklama yeterli.');
    await user.click(screen.getByRole('button', { name: 'Kararı kaydet' }));
    expect(
      await screen.findByText(
        'Karar kaydedilemedi: Alarm #5590 · Kendi yükselttiğiniz alarm için karar veremezsiniz. Hiçbir alarm değiştirilmedi.',
      ),
    ).toBeInTheDocument();
  });

  it('locks final decisions for the user who escalated', async () => {
    server.use(
      http.get(`${API}/alerts/5590`, () =>
        HttpResponse.json(
          alertDetail(escalated, {
            escalated_by: { user_id: 9, actor_name: 'mehmet.ozturk', changed_at: daysAgo(1) },
          }),
        ),
      ),
    );
    storeSession('mehmet.ozturk');
    renderApp('/alerts/5590');
    expect(await screen.findByText('Kendi yükselttiğiniz alarm için karar veremezsiniz.')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Şüpheli olarak onayla' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: 'Analiste geri gönder' })).toBeEnabled();
  });

  it('loads the masked customer context only on request', async () => {
    storeSession('ayse.karaca');
    const { user } = renderApp('/alerts/5518');
    await screen.findByRole('heading', { name: /Alarm #5518/ });
    expect(contextCalls).toBe(0);
    await user.click(screen.getByRole('button', { name: 'Müşteri bilgisini göster' }));
    const table = await screen.findByRole('table', { name: 'Müşteri işlemleri' });
    expect(within(table).getByText('Ö. Kılıç')).toBeInTheDocument();
    expect(screen.getByText('Öğretmen')).toBeInTheDocument();
    expect(screen.getByText('…4410 · TRY')).toBeInTheDocument();
    expect(contextCalls).toBe(1);
    expect(screen.queryByRole('link', { name: /İşlem analizinde aç/ })).not.toBeInTheDocument();
  });

  it('tells analysts that a non-new alert has no customer context', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts/5590');
    expect(
      await screen.findByText('Bu alarm kapanmış. Müşteri bilgisi yalnızca açık alarmlar için görüntülenebilir.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Müşteri bilgisini göster' })).not.toBeInTheDocument();
  });

  it('is read-only for a user who can only view alerts', async () => {
    storeSession('reviewer');
    renderApp('/alerts/5518');
    expect(await screen.findByText('Bu alarm için verebileceğiniz bir karar yok.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Kararı kaydet' })).not.toBeInTheDocument();
  });

  it('shows a not-found state', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts/404404');
    expect(await screen.findByText('Alarm bulunamadı')).toBeInTheDocument();
  });

  it('returns to the queue with its filters', async () => {
    storeSession('ayse.karaca');
    const { user, router } = renderApp('/alerts?severity=high');
    await user.click(await screen.findByRole('button', { name: 'Ahmet Yılmaz için incelemeye başla' }));
    await user.click(await screen.findByRole('link', { name: 'Alarm kuyruğuna dön' }));
    await waitFor(() => expect(router.state.location.search).toBe('?severity=high'));
  });
});
