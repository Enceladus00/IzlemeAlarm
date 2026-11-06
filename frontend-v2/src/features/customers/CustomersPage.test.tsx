import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { CustomerAnalysis, CustomerListItem, CustomerProfile } from '@/api/schemas/customers';
import { alertsHandler } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const customers: CustomerListItem[] = Array.from({ length: 60 }, (_, index) => ({
  customer_no: `C-${String(index + 1).padStart(4, '0')}`,
  full_name: index === 0 ? 'Ahmet Yılmaz' : `Müşteri ${index + 1}`,
  customer_type: index % 5 === 0 ? 'KURUMSAL' : 'BIREYSEL',
  risk_level: 'medium',
  is_active: true,
  account_count: 2,
  open_alert_count: index === 0 ? 3 : 0,
}));

const profile: CustomerProfile = {
  customer_no: 'C-1042',
  full_name: 'Ahmet Yılmaz',
  customer_type: 'BIREYSEL',
  occupation: 'Öğretmen',
  monthly_income: '28000.00',
  risk_level: 'medium',
  is_active: true,
  created_at: '2019-05-01T10:00:00',
  accounts: [
    { account_no: 'TR000000000000000000004410', currency: 'TRY', account_type: 'current', is_active: true, opened_at: '2019-05-02', transaction_count: 64 },
  ],
  alerts: { open: 3, total: 4, by_status: { new: 3, closed: 1 } },
};

/** E12 example from the guide: 121.850 / 28.000 = 4,4 × monthly income. */
function analysisFor(days: number, exceeded = true): CustomerAnalysis {
  return {
    customer_no: 'C-1042',
    days,
    date_from: '2026-08-09',
    date_to: '2026-11-06',
    monthly: [
      { month: '2026-10', currency: 'TRY', incoming: '40000.00', outgoing: '35000.00' },
      { month: '2026-11', currency: 'TRY', incoming: '121850.00', outgoing: '9000.00' },
      { month: '2026-11', currency: 'USD', incoming: '500.00', outgoing: '0.00' },
    ],
    income_check: {
      monthly_income: '28000.00',
      currency: 'TRY',
      peak_month: '2026-11',
      peak_direction: 'incoming',
      peak_amount: '121850.00',
      ratio: exceeded ? '4.4' : '1.4',
      threshold: '3',
      exceeded,
    },
    counterparties: {
      incoming: [
        { account_no: 'TR11', customer_no: 'C-9', customer_name: 'Yeni Gönderen', currency: 'TRY', count: 3, amount: '100000.00', is_new: true },
        { account_no: 'TR12', customer_no: 'C-8', customer_name: 'Eski Tanıdık', currency: 'TRY', count: 5, amount: '21850.00', is_new: false },
      ],
      outgoing: [],
    },
  };
}

const analysisRequests: URLSearchParams[] = [];
const customerRequests: URLSearchParams[] = [];
const accountRequests: URLSearchParams[] = [];

beforeEach(() => {
  customerRequests.length = 0;
  accountRequests.length = 0;
  analysisRequests.length = 0;
  server.use(
    http.get(`${API}/customers/C-1042/analysis`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      analysisRequests.push(params);
      return HttpResponse.json(analysisFor(Number(params.get('days'))));
    }),
    ...alertsHandler(),
    http.get(`${API}/customers`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      customerRequests.push(params);
      const q = (params.get('q') ?? '').toLocaleLowerCase('tr-TR');
      const filtered = customers
        .filter((item) => !q || item.full_name.toLocaleLowerCase('tr-TR').includes(q) || item.customer_no.toLowerCase().includes(q))
        .filter((item) => !params.get('customer_type') || item.customer_type === params.get('customer_type'));
      const offset = Number(params.get('offset') ?? 0);
      const limit = Number(params.get('limit') ?? 50);
      return HttpResponse.json({ total: filtered.length, items: filtered.slice(offset, offset + limit) });
    }),
    http.get(`${API}/customers/C-1042`, () => HttpResponse.json(profile)),
    http.get(`${API}/customers/NOPE`, () => HttpResponse.json({ detail: 'Customer not found.' }, { status: 404 })),
    http.get(`${API}/accounts`, ({ request }) => {
      accountRequests.push(new URL(request.url).searchParams);
      return HttpResponse.json({
        total: 1,
        items: [
          { account_no: 'TR000000000000000000004410', customer_no: 'C-1042', customer_name: 'Ahmet Yılmaz', currency: 'TRY', account_type: 'current', is_active: true, opened_at: '2019-05-02' },
        ],
      });
    }),
  );
});

describe('Customers', () => {
  it('lists customers, searches and filters on the server and pages', async () => {
    storeSession('mehmet.ozturk');
    const { user, router } = renderApp('/customers');
    const table = await screen.findByRole('table', { name: 'Müşteriler' });
    expect(within(table).getByRole('link', { name: 'Ahmet Yılmaz' })).toHaveAttribute('href', '/customers/C-0001');
    expect(screen.getByText('60 müşteri')).toBeInTheDocument();
    expect(accountRequests).toHaveLength(0); // the accounts tab is not loaded

    await user.click(screen.getByRole('button', { name: /Sonraki/ }));
    await waitFor(() => expect(customerRequests.at(-1)!.get('offset')).toBe('50'));

    await user.selectOptions(screen.getByLabelText('Müşteri tipi'), 'KURUMSAL');
    await waitFor(() => expect(customerRequests.at(-1)!.get('customer_type')).toBe('KURUMSAL'));
    expect(customerRequests.at(-1)!.get('offset')).toBe('0');

    await user.type(screen.getByRole('searchbox', { name: 'Müşteri no veya ad' }), 'ahmet');
    await waitFor(() => expect(router.state.location.search).toContain('q=ahmet'));
    await waitFor(() => expect(customerRequests.at(-1)!.get('q')).toBe('ahmet'));
  });

  it('shows the accounts tab only when chosen', async () => {
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/customers');
    await screen.findByRole('table', { name: 'Müşteriler' });
    await user.click(screen.getByRole('tab', { name: 'Hesaplar' }));
    const table = await screen.findByRole('table', { name: 'Hesaplar' });
    expect(within(table).getByText('TR000000000000000000004410')).toBeInTheDocument();
    expect(screen.getByText(/her sayfa denetim kaydına yazılır/)).toBeInTheDocument();
    expect(accountRequests).toHaveLength(1);
  });

  it('opens a customer profile with accounts and alerts', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/customers/C-1042');
    expect(await screen.findByRole('heading', { name: 'Ahmet Yılmaz' })).toBeInTheDocument();
    expect(screen.getByText('Öğretmen')).toBeInTheDocument();
    expect(screen.getByText('3 açık · toplam 4')).toBeInTheDocument();
    const accounts = screen.getByRole('table', { name: 'Hesaplar' });
    expect(within(accounts).getByRole('link', { name: 'TR000000000000000000004410' })).toHaveAttribute(
      'href',
      '/transactions?customer=C-1042&focus=account%3ATR000000000000000000004410',
    );
    expect(await screen.findByRole('link', { name: /#5518/ })).toBeInTheDocument();
  });

  it('analyses the customer: income warning, monthly bars and new counterparties (E12)', async () => {
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/customers/C-1042');
    const section = await screen.findByRole('region', { name: 'Müşteri ve işlem analizi' });
    expect(await within(section).findByText(/121\.850,00 TRY, beyan edilen aylık gelirin \(28\.000,00 TRY\) 4,4 katı/)).toBeInTheDocument();
    expect(within(section).getAllByTestId('month-group')).toHaveLength(2); // TRY first, USD not mixed in
    const senders = within(section).getByRole('table', { name: 'Para gönderenler' });
    const rows = within(senders).getAllByRole('row').slice(1);
    expect(within(rows[0]!).getByText('YENİ')).toBeInTheDocument();
    expect(within(rows[1]!).queryByText('YENİ')).not.toBeInTheDocument();
    expect(within(rows[0]!).getByText('%82')).toBeInTheDocument();
    expect(within(section).getByText('Bu dönemde karşı taraf yok.')).toBeInTheDocument();
    expect(analysisRequests[0]!.get('days')).toBe('90');

    await user.selectOptions(within(section).getByLabelText('Dönem'), '30');
    await waitFor(() => expect(analysisRequests.map((params) => params.get('days'))).toContain('30'));
  });

  it('shows no income warning below the threshold', async () => {
    server.use(http.get(`${API}/customers/C-1042/analysis`, () => HttpResponse.json(analysisFor(90, false))));
    storeSession('mehmet.ozturk');
    renderApp('/customers/C-1042');
    const section = await screen.findByRole('region', { name: 'Müşteri ve işlem analizi' });
    await within(section).findByRole('table', { name: 'Para gönderenler' });
    expect(within(section).queryByText('Gelirle uyumsuz hacim')).not.toBeInTheDocument();
  });

  it('shows a not-found state', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/customers/NOPE');
    expect(await screen.findByText('Müşteri bulunamadı')).toBeInTheDocument();
  });

  it('is limited to customer:view', async () => {
    storeSession('ayse.karaca');
    renderApp('/customers');
    expect(await screen.findByText('Bu sayfaya erişim yetkiniz yok')).toBeInTheDocument();
    expect(customerRequests).toHaveLength(0);
  });
});
