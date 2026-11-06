import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { dashboardFixture, emptyDashboardFixture } from '@/test/fixtures';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

describe('Detection overview', () => {
  it('shows locale-formatted KPIs, severity, rules and latest alerts', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/overview');

    expect(await screen.findByText('186.420')).toBeInTheDocument();
    expect(screen.getByText('4.790')).toBeInTheDocument();
    expect(screen.getByText('17 açık alarm')).toBeInTheDocument();
    expect(screen.getByText('2.317 hesap')).toBeInTheDocument();

    const severity = screen.getByRole('table', { name: 'Alarm önem dağılımı' });
    expect(within(severity).getByText('Yüksek')).toBeInTheDocument();
    expect(within(severity).getByText('6')).toBeInTheDocument();

    const rules = screen.getByRole('table', { name: 'En sık tetiklenen kurallar' });
    const ruleCodes = within(rules).getAllByRole('rowheader').map((cell) => cell.textContent);
    expect(ruleCodes).toEqual(['R05', 'R01', 'R10']);
    expect(screen.getByText('2 kural henüz alarm üretmedi.')).toBeInTheDocument();

    expect(await screen.findByText('Ahmet Yılmaz')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '#5531' })).toHaveAttribute('href', '/alerts?alert=5531');
    expect(screen.getByText('Uyum onayında')).toBeInTheDocument();
    expect(screen.getByText('26.10.2026 16:40')).toBeInTheDocument();
  });

  it('offers the trend as an accessible table', async () => {
    storeSession('admin');
    const { user } = renderApp('/overview');
    expect(await screen.findByRole('group', { name: 'Tespit eğilimi · son 30 gün' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Tablo olarak göster' }));
    expect(screen.getByRole('columnheader', { name: 'Şüpheli işlemler' })).toBeInTheDocument();
    expect(screen.getByText('05.10.2026')).toBeInTheDocument();
  });

  it('runs rule evaluation for rule:edit and reports created alerts', async () => {
    let calls = 0;
    server.use(
      http.post(`${API}/rules/evaluate`, () => {
        calls += 1;
        return HttpResponse.json({ created_alerts: 4 });
      }),
    );
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/overview');
    await user.click(await screen.findByRole('button', { name: 'Kuralları şimdi çalıştır' }));
    expect(await screen.findByText('Değerlendirme tamamlandı: 4 yeni alarm oluşturuldu.')).toBeInTheDocument();
    expect(calls).toBe(1);
  });

  it('hides evaluation without rule:edit', async () => {
    storeSession('ayse.karaca');
    renderApp('/overview');
    expect(await screen.findByText('186.420')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Kuralları şimdi çalıştır' })).not.toBeInTheDocument();
  });

  it('does not request alerts without alert:view', async () => {
    let alertCalls = 0;
    server.use(
      http.get(`${API}/alerts`, () => {
        alertCalls += 1;
        return HttpResponse.json({ total: 0, items: [] });
      }),
    );
    storeSession('viewer');
    renderApp('/overview');
    expect(await screen.findByText('Hesabınız alarm ayrıntılarını görüntüleyemez.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Tüm alarmlar' })).not.toBeInTheDocument();
    expect(alertCalls).toBe(0);
  });

  it('shows empty states for a fresh database', async () => {
    server.use(
      http.get(`${API}/dashboard/summary`, () => HttpResponse.json(emptyDashboardFixture)),
      http.get(`${API}/alerts`, () => HttpResponse.json({ total: 0, items: [] })),
    );
    storeSession('mehmet.ozturk');
    renderApp('/overview');
    expect(await screen.findByText('Henüz alarm üretilmedi.')).toBeInTheDocument();
    expect(screen.getByText('Henüz alarm üreten kural yok.')).toBeInTheDocument();
    expect(screen.getByText('Son 30 günde alarm veya şüpheli işlem kaydı yok.')).toBeInTheDocument();
    expect(await screen.findByText(/Henüz alarm yok/)).toBeInTheDocument();
  });

  it('shows a retryable error when the API is unavailable', async () => {
    let fail = true;
    server.use(
      http.get(`${API}/dashboard/summary`, () =>
        fail ? HttpResponse.json({ detail: 'Could not load dashboard.' }, { status: 503 }) : undefined,
      ),
    );
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/overview');
    expect(await screen.findByText('Genel bakış yüklenemedi.')).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Yeniden dene' }));
    expect(await screen.findByText('186.420')).toBeInTheDocument();
  });

  it('loads only the summary first, other tabs on demand, and re-queries the period (K3)', async () => {
    const requests: string[] = [];
    server.use(
      http.get(`${API}/dashboard/summary`, ({ request }) => {
        requests.push(`summary?${new URL(request.url).searchParams}`);
        return HttpResponse.json({ ...dashboardFixture, days: Number(new URL(request.url).searchParams.get('days')) });
      }),
      http.get(`${API}/dashboard/funnel`, ({ request }) => {
        requests.push(`funnel?${new URL(request.url).searchParams}`);
        return HttpResponse.json({
          days: 30,
          created: 10,
          open: 3,
          confirmed: 1,
          escalation_rate: 0.2,
          confirmed_rate: 1,
          avg_decision_days: 2.5,
          analyst_closed: 6,
          analyst_open: 2,
          escalated: 2,
          escalation_outcome: { confirmed: 1, closed: 0, returned: 1, pending: 0 },
        });
      }),
      http.get(`${API}/dashboard/rule-performance`, ({ request }) => {
        requests.push(`rules?${new URL(request.url).searchParams}`);
        return HttpResponse.json([
          { rule_code: 'R05', name: 'Olağandışı tutar', is_active: true, evaluated: 1830, alerts: 42, avg_alert_score: '0.7811', confirmed: 6, closed: 30, hit_rate: 0.167, provisional: true },
        ]);
      }),
    );
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/overview');
    expect(await screen.findByText('186.420')).toBeInTheDocument();
    expect(requests).toEqual(['summary?days=30']);

    await user.click(screen.getByRole('tab', { name: 'Alarm akışı' }));
    expect(await screen.findByText('Analist kapattı')).toBeInTheDocument();
    // E10 KPIs; the daily chart reuses the cached summary, so no extra request.
    expect(screen.getByText('Yükseltme oranı').parentElement).toHaveTextContent('%20');
    expect(screen.getByText('Ort. karar süresi').parentElement).toHaveTextContent('2,5 gün');
    expect(screen.getByText('Açık alarm').parentElement).toHaveTextContent('3');
    expect(screen.getByTestId('escalation-accuracy')).toHaveTextContent('%100');
    expect(screen.getByTestId('escalation-accuracy')).toHaveTextContent('1 onaylandı / 1 karar');
    expect(screen.getAllByTestId('daily-bar')).toHaveLength(dashboardFixture.trends.length);
    expect(requests).toEqual(['summary?days=30', 'funnel?days=30']);

    await user.click(screen.getByRole('tab', { name: 'Kurallar' }));
    const table = await screen.findByRole('table', { name: 'Kural başarımı · son 30 gün' });
    expect(within(table).getByText('%16,7')).toBeInTheDocument();
    expect(within(table).getByText('Geçici')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Dönem'), '7');
    await waitFor(() => expect(requests).toContain('rules?days=7'));
    expect(requests.some((item) => item.startsWith('summary?days=7'))).toBe(false);
  });
});
