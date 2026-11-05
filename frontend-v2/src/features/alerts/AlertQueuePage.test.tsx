import { screen, waitFor, within } from '@testing-library/react';
import { alertRequests, alertsHandler, makeAlert, queueAlerts, queueRequests } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { server } from '@/test/server';

/** The queue page's own request (the navigation badge also asks with limit=1). */
function pageRequest() {
  return queueRequests.find((params) => params.get('limit') === '50')!;
}

function queueList() {
  return screen.getAllByRole('list').find((list) => list.querySelector('[aria-expanded]'))!;
}

beforeEach(() => {
  alertRequests.length = 0;
  queueRequests.length = 0;
  server.use(...alertsHandler());
});

describe('Alert queue (K1: grouped on the server)', () => {
  it('lists customers in the server order with summary totals', async () => {
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
    expect(screen.getByText('5 müşteri', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('3 müşteri', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('5 müşteri · 8 alarm')).toBeInTheDocument();
    expect(screen.getByText('4 gün')).toBeInTheDocument();
    expect(screen.getByText('Kurumsal')).toBeInTheDocument();
    expect(pageRequest().get('status')).toBe('new');
    expect(pageRequest().get('sort')).toBe('severity_age');
  });

  it('fills the personal KPI cards from /dashboard/my-summary', async () => {
    server.use(...alertsHandler(queueAlerts, { 'C-0877': 'mehmet.ozturk' }));
    storeSession('ayse.karaca');
    renderApp('/alerts');
    await screen.findByText('Ahmet Yılmaz');
    expect(await screen.findByText('2 alarm uyuma yükseltildi')).toBeInTheDocument();
    expect(screen.getByText('Geri gönderildi · mehmet.ozturk')).toBeInTheDocument();
    expect(document.querySelectorAll('[data-placeholder]')).toHaveLength(0);
  });

  it('expands a customer to list its alerts in this status', async () => {
    storeSession('ayse.karaca');
    const { user } = renderApp('/alerts');
    const toggle = await screen.findByRole('button', { name: 'Ahmet Yılmaz alarmlarını göster' });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const panel = document.getElementById(toggle.getAttribute('aria-controls')!)!;
    await waitFor(() => expect(within(panel).getAllByRole('link')).toHaveLength(3));
    const links = within(panel).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href')).sort()).toEqual(['/alerts/5518', '/alerts/5524', '/alerts/5531']);
    expect(alertRequests.some((params) => params.get('customer_no') === 'C-1042' && params.get('status') === 'new')).toBe(true);
  });

  it('sends filters to the server and keeps them in the URL', async () => {
    storeSession('ayse.karaca');
    const { user, router } = renderApp('/alerts');
    await screen.findByText('Ahmet Yılmaz');

    await user.click(screen.getByRole('button', { name: /Önem: Tümü/ }));
    await user.click(screen.getByRole('radio', { name: 'Yüksek' }));

    await waitFor(() => expect(router.state.location.search).toBe('?severity=high'));
    await waitFor(() => expect(queueRequests.some((params) => params.get('severity') === 'high')).toBe(true));
    expect(await screen.findByText('3 müşteri · 3 alarm')).toBeInTheDocument();
    expect(screen.queryByText('Mert Demir')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Filtreleri temizle' }));
    await waitFor(() => expect(router.state.location.search).toBe(''));
  });

  it('searches on the server', async () => {
    storeSession('ayse.karaca');
    const { user, router } = renderApp('/alerts');
    await screen.findByText('Ahmet Yılmaz');
    await user.type(screen.getByRole('searchbox', { name: 'Müşteri no veya ad ara' }), 'tekstil');
    await waitFor(() => expect(router.state.location.search).toBe('?q=tekstil'));
    await waitFor(() => expect(screen.queryByText('Ahmet Yılmaz')).not.toBeInTheDocument());
    expect(screen.getByText('Kaya Tekstil Ltd. Şti.')).toBeInTheDocument();
    expect(queueRequests.some((params) => params.get('q') === 'tekstil')).toBe(true);
  });

  it('pages through customers with offsets', async () => {
    const many = Array.from({ length: 120 }, (_, index) =>
      makeAlert({ customer_no: `C-${String(index).padStart(3, '0')}`, customer_name: `Müşteri ${index}` }),
    );
    server.use(...alertsHandler(many));
    storeSession('ayse.karaca');
    const { user } = renderApp('/alerts');
    expect(await screen.findByText('120 müşteri · 120 alarm')).toBeInTheDocument();
    expect(screen.getByText('Sayfa 1 / 3')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Sonraki/ }));
    expect(await screen.findByText('Sayfa 2 / 3')).toBeInTheDocument();
    expect(queueRequests.some((params) => params.get('offset') === '50')).toBe(true);
    expect(screen.queryByText(/Gruplar yalnızca yüklenen/)).not.toBeInTheDocument();
  });

  it('defaults compliance officers to escalated cases, longest waiting first', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/alerts');
    expect(await screen.findByText('Deniz Kurt')).toBeInTheDocument();
    expect(pageRequest().get('status')).toBe('in_review');
    expect(pageRequest().get('sort')).toBe('waiting');
  });

  it('shows compliance who escalated, why, and how long the case has waited (E04)', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/alerts');
    await screen.findByText('Deniz Kurt');
    expect(screen.getByText('ayse.karaca')).toBeInTheDocument();
    expect(screen.getByText('Profil dışı giden işlem')).toBeInTheDocument();
    expect(screen.getByText('Analistin notu:')).toBeInTheDocument();
    // Escalated 6 days ago: over the 2-day mark, so it is highlighted.
    expect(screen.getByText('6 gündür bekliyor')).toHaveClass('text-warning');
  });

  it('validates a custom date range before requesting', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts?range=custom&from=2026-10-10&to=2026-10-01');
    expect(await screen.findByText('Başlangıç tarihi bitiş tarihinden sonra olamaz.')).toBeInTheDocument();
    expect(queueRequests.some((params) => params.get('date_from') === '2026-10-10')).toBe(false);
  });

  it('shows an empty queue', async () => {
    server.use(...alertsHandler([]));
    storeSession('ayse.karaca');
    renderApp('/alerts');
    expect(await screen.findByText('Bekleyen alarm yok')).toBeInTheDocument();
  });

  it('shows the open-alert count in the navigation', async () => {
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

  it('opens the customer’s oldest alert when reviewing', async () => {
    storeSession('ayse.karaca');
    const { user, router } = renderApp('/alerts?severity=high');
    await user.click(await screen.findByRole('button', { name: 'Kaya Tekstil Ltd. Şti. için incelemeye başla' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/alerts/5540'));
  });
});
