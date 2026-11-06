import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { alertsHandler, queueAlerts, queueRequests } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

beforeEach(() => {
  queueRequests.length = 0;
  server.use(...alertsHandler());
});

describe('My panel (E08)', () => {
  it('is the analyst landing page with the four numbers', async () => {
    storeSession('ayse.karaca');
    const { router } = renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Merhaba, ayse.karaca' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/my-panel');
    const queued = queueAlerts.filter((alert) => alert.status === 'new');
    expect((await screen.findByText('Kuyrukta bekleyen')).parentElement).toHaveTextContent(String(queued.length));
    expect(screen.getByText('Bugün kapattığım').parentElement).toHaveTextContent('2');
    expect(screen.getByText('1 tanesi şüpheli onaylandı')).toBeInTheDocument();
  });

  it('hides the returned box when nothing was returned, shows it otherwise', async () => {
    storeSession('ayse.karaca');
    const first = renderApp('/my-panel');
    await screen.findByText('Bugün kapattığım');
    expect(screen.queryByRole('region', { name: 'Geri gönderilen vakalar' })).not.toBeInTheDocument();
    first.unmount();

    server.use(...alertsHandler(queueAlerts, { 'C-0877': 'mehmet.ozturk' }));
    renderApp('/my-panel');
    const box = await screen.findByRole('region', { name: 'Geri gönderilen vakalar' });
    expect(within(box).getByText('Eksik belge')).toBeInTheDocument();
    expect(within(box).getByRole('link', { name: /İncelemeye dön/ })).toHaveAttribute('href', '/alerts/1');
  });

  it('shows escalation outcomes adding up to the 30-day count, the first three customers and today\'s decisions', async () => {
    storeSession('ayse.karaca');
    renderApp('/my-panel');
    const legend = await screen.findByTestId('outcome-legend');
    const values = within(legend).getAllByRole('definition').map((node) => Number(node.textContent));
    expect(values).toEqual([3, 2, 1, 1]);
    expect(values.reduce((a, b) => a + b, 0)).toBe(7);
    expect(screen.getByText(/yükselttiğim 7 alarmın/)).toBeInTheDocument();

    const first = await screen.findByRole('list', { name: 'Önce bunlara bak' });
    expect(within(first).getAllByRole('listitem')).toHaveLength(3);
    const request = queueRequests.find((params) => params.get('limit') === '3')!;
    expect(request.get('status')).toBe('new');

    const table = screen.getByRole('table', { name: 'Bugünkü kararlarım' });
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    expect(within(table).getByRole('link', { name: 'Mert Kaya' })).toHaveAttribute('href', '/alerts/2');
  });

  it('does not break when the summary endpoint is missing', async () => {
    server.use(http.get(`${API}/dashboard/my-summary`, () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })));
    storeSession('ayse.karaca');
    renderApp('/my-panel');
    expect(await screen.findByText(/B8 \/dashboard\/my-summary gerekli/)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Kuyruğa git' }).length).toBeGreaterThan(0);
  });
});
