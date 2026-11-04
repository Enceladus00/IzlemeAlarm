import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { systemOverviewFixture } from '@/test/fixtures';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

describe('System overview', () => {
  it('shows health, record volume and security configuration', async () => {
    storeSession('admin');
    renderApp('/system');

    expect(await screen.findByText('Bağlı')).toBeInTheDocument();
    expect(screen.getByText('Çalışıyor')).toBeInTheDocument();
    expect(screen.getByText(/GET \/health · 200 · \d+ ms/)).toBeInTheDocument();
    expect(screen.getByText('SELECT 1 · 2,1 ms')).toBeInTheDocument();
    expect(screen.getByText('alembic · 0006_alert_workflow')).toBeInTheDocument();
    expect(screen.getByText('18 kural aktif')).toBeInTheDocument();
    expect(screen.getByText('son çalışma 29.10.2026 18:42 · 2,4 sn')).toBeInTheDocument();

    const customers = screen.getByRole('rowheader', { name: 'Müşteri' }).closest('tr')!;
    expect(within(customers).getByText('1.284')).toBeInTheDocument();
    expect(within(customers).getByText('+96')).toBeInTheDocument();
    const accounts = screen.getByRole('rowheader', { name: 'Hesap' }).closest('tr')!;
    expect(within(accounts).getByText('—')).toBeInTheDocument();

    expect(screen.getByText('30 dk')).toBeInTheDocument();
    expect(screen.getByText('Kapalı')).toBeInTheDocument();
    expect(screen.getByText('4 / 5')).toBeInTheDocument();
    expect(screen.getByText('5 MB · 5.000 satır')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Denetim kaydını aç/ })).toHaveAttribute('href', '/audit');
  });

  it('shows the schema as up to date when revision matches head', async () => {
    storeSession('admin');
    renderApp('/system');
    expect(await screen.findByText('Güncel')).toBeInTheDocument();
    expect(screen.queryByText('Yer tutucu')).not.toBeInTheDocument();
  });

  it('warns when the database schema is behind the server head', async () => {
    server.use(
      http.get(`${API}/admin/system-overview`, () => {
        return HttpResponse.json({
          ...systemOverviewFixture,
          health: { ...systemOverviewFixture.health, schema_revision: '0006_alert_workflow', schema_head: '0007_future' },
        });
      }),
    );
    storeSession('admin');
    renderApp('/system');
    expect(await screen.findByText('Güncel değil: 0007_future bekleniyor')).toBeInTheDocument();
  });

  it('reports an unreachable API health check', async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.json({ detail: 'Database unavailable.' }, { status: 503 })));
    storeSession('admin');
    renderApp('/system');
    expect(await screen.findByText('Erişilemiyor')).toBeInTheDocument();
    expect(screen.getByText('GET /health · 503')).toBeInTheDocument();
  });

  it('shows the server permission error if access is revoked mid-session', async () => {
    server.use(
      http.get(`${API}/admin/system-overview`, () =>
        HttpResponse.json({ detail: 'Permission required: user:manage.' }, { status: 403 }),
      ),
    );
    storeSession('admin');
    renderApp('/system');
    expect(await screen.findByText('Bu işlem için yetkiniz yok.')).toBeInTheDocument();
  });

  it('is not reachable for an analyst', async () => {
    storeSession('ayse.karaca');
    renderApp('/system');
    expect(await screen.findByText('Bu sayfaya erişim yetkiniz yok')).toBeInTheDocument();
  });
});
