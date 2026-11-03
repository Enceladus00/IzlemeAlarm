import { screen, waitFor, within } from '@testing-library/react';
import { alertRequests, alertsHandler, makeAlert, queueAlerts } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { server } from '@/test/server';

function queueList() {
  return screen.getAllByRole('list').find((list) => list.querySelector('[aria-expanded]'))!;
}

beforeEach(() => {
  alertRequests.length = 0;
  server.use(alertsHandler());
});

describe('Alert queue', () => {
  it('groups new alerts by customer in severity/age order with KPI totals', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts');

    expect(await screen.findByText('Ahmet Yılmaz')).toBeInTheDocument();
    const rows = within(queueList()).getAllByRole('button', { name: /alarmlarını göster/ });
    expect(rows.map((row) => row.getAttribute('aria-label'))).toEqual([
      'Ahmet Yılmaz alarmlarını göster',
      'Kaya Tekstil Ltd. Şti. alarmlarını göster',
      'Selin Arslan alarmlarını göster',
      'Mert Demir alarmlarını göster',
      'Burak Aydın alarmlarını göster',
    ]);
    // 8 new alerts from 5 customers; 3 high from 3 customers.
    expect(screen.getByText('5 müşteri')).toBeInTheDocument();
    expect(screen.getByText('3 müşteri')).toBeInTheDocument();
    expect(screen.getByText('5 müşteri · 8 alarm gösteriliyor')).toBeInTheDocument();
    expect(screen.getByText('4 gün')).toBeInTheDocument();
    expect(screen.getAllByText('Bugün').length).toBeGreaterThan(0);
  });

  it('marks fields the API cannot supply as placeholders', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts');
    await screen.findByText('Ahmet Yılmaz');
    expect(screen.getByText('Bugün kararlaştırdığım').parentElement!.querySelector('[data-placeholder]')).not.toBeNull();
    expect(screen.getByText('Bana geri gönderilen').parentElement!.querySelector('[data-placeholder]')).not.toBeNull();
    expect(document.querySelectorAll('[data-placeholder]').length).toBeGreaterThanOrEqual(7);
  });

  it('expands a customer to list each alert with a link to its detail', async () => {
    storeSession('ayse.karaca');
    const { user } = renderApp('/alerts');
    const toggle = await screen.findByRole('button', { name: 'Ahmet Yılmaz alarmlarını göster' });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const links = within(document.getElementById(toggle.getAttribute('aria-controls')!)!).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual(['/alerts/5518', '/alerts/5524', '/alerts/5531']);
    expect(within(links[2]!).getByText(/skor 0,94/)).toBeInTheDocument();
  });

  it('sends chosen filters to the API and keeps them in the URL', async () => {
    storeSession('ayse.karaca');
    const { user, router } = renderApp('/alerts');
    await screen.findByText('Ahmet Yılmaz');

    await user.click(screen.getByRole('button', { name: /Önem: Tümü/ }));
    await user.click(screen.getByRole('radio', { name: 'Yüksek' }));

    await waitFor(() => expect(router.state.location.search).toBe('?severity=high'));
    await waitFor(() =>
      expect(alertRequests.some((params) => params.get('severity') === 'high' && params.get('status') === 'new' && params.get('limit') === '200')).toBe(true),
    );
    expect(await screen.findByText('3 müşteri · 3 alarm gösteriliyor')).toBeInTheDocument();
    expect(screen.queryByText('Mert Demir')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Filtreleri temizle' }));
    await waitFor(() => expect(router.state.location.search).toBe(''));
  });

  it('shows every status when the status filter is cleared', async () => {
    storeSession('ayse.karaca');
    const { user } = renderApp('/alerts?status=all');
    const toggle = await screen.findByRole('button', { name: 'Burak Aydın alarmlarını göster' });
    await user.click(toggle);
    expect(within(document.getElementById(toggle.getAttribute('aria-controls')!)!).getByText('Kapatıldı')).toBeInTheDocument();
  });

  it('filters loaded customers by search text', async () => {
    storeSession('ayse.karaca');
    const { user } = renderApp('/alerts');
    await screen.findByText('Ahmet Yılmaz');
    await user.type(screen.getByRole('searchbox', { name: 'Müşteri no veya ad ara' }), 'tekstil');
    expect(screen.queryByText('Ahmet Yılmaz')).not.toBeInTheDocument();
    expect(screen.getByText('Kaya Tekstil Ltd. Şti.')).toBeInTheDocument();
    await user.clear(screen.getByRole('searchbox'));
    await user.type(screen.getByRole('searchbox'), 'zzz');
    expect(screen.getByText('“zzz” ile eşleşen müşteri yok.')).toBeInTheDocument();
  });

  it('pages beyond 200 alerts and warns that groups are partial', async () => {
    const many = Array.from({ length: 250 }, (_, index) =>
      makeAlert({ customer_no: `C-${index % 40}`, customer_name: `Müşteri ${index % 40}` }),
    );
    server.use(alertsHandler(many));
    storeSession('ayse.karaca');
    const { user } = renderApp('/alerts');
    expect(await screen.findByText('40 müşteri · 200 / 250 alarm yüklendi')).toBeInTheDocument();
    expect(screen.getByText(/Gruplar yalnızca yüklenen alarmlara göre/)).toBeInTheDocument();
    expect(screen.getByText('en az 40 müşteri', { selector: 'p' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Sonraki 50 alarmı yükle' }));
    expect(await screen.findByText('40 müşteri · 250 alarm gösteriliyor')).toBeInTheDocument();
    expect(alertRequests.some((params) => params.get('offset') === '200')).toBe(true);
  });

  it('validates a custom date range before requesting', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts?range=custom&from=2026-10-10&to=2026-10-01');
    expect(await screen.findByText('Başlangıç tarihi bitiş tarihinden sonra olamaz.')).toBeInTheDocument();
    expect(alertRequests.some((params) => params.get('date_from') === '2026-10-10')).toBe(false);
  });

  it('shows an empty queue', async () => {
    server.use(alertsHandler([]));
    storeSession('ayse.karaca');
    renderApp('/alerts');
    expect(await screen.findByText('Bekleyen alarm yok')).toBeInTheDocument();
  });

  it('shows the new-alert count in the navigation', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts');
    const link = (await screen.findAllByRole('link', { name: /Alarm inceleme/ }))[0]!;
    await waitFor(() => expect(within(link).getByText('8')).toBeInTheDocument());
  });

  it('redirects old ?alert= links to the detail page', async () => {
    storeSession('ayse.karaca');
    const { router } = renderApp('/alerts?alert=5518');
    await waitFor(() => expect(router.state.location.pathname).toBe('/alerts/5518'));
  });

  it('opens the first (most severe) alert when reviewing a customer', async () => {
    storeSession('ayse.karaca');
    const { user, router } = renderApp('/alerts?severity=high');
    await user.click(await screen.findByRole('button', { name: 'Kaya Tekstil Ltd. Şti. için incelemeye başla' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/alerts/5540'));
    expect(queueAlerts.find((alert) => alert.alert_id === 5540)?.severity).toBe('high');
  });
});
