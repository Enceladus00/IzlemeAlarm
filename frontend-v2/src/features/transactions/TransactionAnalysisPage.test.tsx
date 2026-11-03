import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { Transaction } from '@/api/schemas/transactions';
import { sampleTransaction } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const requests: URLSearchParams[] = [];

function makeTx(index: number, partial: Partial<Transaction> = {}): Transaction {
  return {
    ...sampleTransaction,
    transaction_id: index,
    transaction_no: `TX-${String(index).padStart(4, '0')}`,
    amount: '1000.00',
    tx_time: `2026-10-${String((index % 20) + 1).padStart(2, '0')}T10:00:00`,
    alert_linked: index % 3 === 0,
    ...partial,
  };
}

/** Mimics GET /transactions filtering by customer/account/direction plus paging. */
function transactionsHandler(dataset: Transaction[]) {
  return http.get(`${API}/transactions`, ({ request }) => {
    const params = new URL(request.url).searchParams;
    requests.push(params);
    const customer = params.get('customer_no');
    const account = params.get('account_no');
    const direction = params.get('direction');
    const filtered = dataset.filter((tx) => {
      const outgoing = (customer && tx.sender_customer_no === customer) || (account && tx.sender_account_no === account);
      const incoming = (customer && tx.receiver_customer_no === customer) || (account && tx.receiver_account_no === account);
      if (!customer && !account) return true;
      if (direction === 'outgoing') return outgoing;
      if (direction === 'incoming') return incoming;
      return outgoing || incoming;
    });
    const offset = Number(params.get('offset') ?? 0);
    const limit = Number(params.get('limit') ?? 200);
    return HttpResponse.json({ total: filtered.length, items: filtered.slice(offset, offset + limit) });
  });
}

const dataset = [
  makeTx(1),
  makeTx(2, { currency: 'USD', amount: '50.00' }),
  makeTx(3, {
    sender_customer_no: 'C-0311',
    sender_customer_name: 'Kaya Tekstil Ltd. Şti.',
    sender_account_no: 'TR-ACC-0311',
    receiver_customer_no: 'C-1042',
    receiver_customer_name: 'Ahmet Yılmaz',
    receiver_account_no: 'TR-ACC-1042',
    amount: '250.50',
  }),
];

beforeEach(() => {
  requests.length = 0;
  server.use(transactionsHandler(dataset));
});

describe('Transaction analysis', () => {
  it('shows totals per currency when no customer is selected', async () => {
    storeSession('admin');
    renderApp('/transactions');
    expect(await screen.findByText('3 eşleşen işlem · 3 gösteriliyor')).toBeInTheDocument();
    expect(screen.getByText('1.250,50 TRY · 50,00 USD')).toBeInTheDocument();
    expect(screen.getByText('Müşteri seçilmediği için yön ayrımı yapılmaz.')).toBeInTheDocument();
    expect(screen.queryByText('Gelen tutar')).not.toBeInTheDocument();
    expect(requests[0]!.get('limit')).toBe('500');
  });

  it('splits incoming and outgoing for a customer from an alert link', async () => {
    storeSession('admin');
    renderApp('/transactions?customer=C-1042');
    expect(await screen.findByText('Gelen tutar')).toBeInTheDocument();
    expect(screen.getByText('Gelen tutar').parentElement).toHaveTextContent('250,50 TRY');
    expect(screen.getByText('Giden tutar').parentElement).toHaveTextContent('1.000,00 TRY · 50,00 USD');
    expect(screen.getByLabelText('Müşteri numarası')).toHaveValue('C-1042');
    expect(requests.at(-1)!.get('customer_no')).toBe('C-1042');
    const table = screen.getByRole('table', { name: 'Transferler' });
    // Column header + at least one flagged row (TX-0003 is alert-linked).
    expect(within(table).getAllByText('Alarm bağlantılı').length).toBeGreaterThan(1);
  });

  it('validates filters before sending them', async () => {
    storeSession('admin');
    const { user, router } = renderApp('/transactions');
    await screen.findByText('3 eşleşen işlem · 3 gösteriliyor');

    await user.selectOptions(screen.getByLabelText('Yön'), 'outgoing');
    await user.type(screen.getByLabelText('En düşük tutar'), '500');
    await user.type(screen.getByLabelText('En yüksek tutar'), '100');
    await user.click(screen.getByRole('button', { name: 'İşlemleri analiz et' }));
    expect(screen.getByText('Gelen veya giden yönü analiz etmek için müşteri numarası girin.')).toBeInTheDocument();
    expect(screen.getByText('En düşük tutar en yüksek tutarı aşamaz.')).toBeInTheDocument();
    expect(router.state.location.search).toBe('');

    await user.type(screen.getByLabelText('Müşteri numarası'), 'C-1042');
    await user.clear(screen.getByLabelText('En yüksek tutar'));
    await user.click(screen.getByRole('button', { name: 'İşlemleri analiz et' }));
    await waitFor(() => expect(router.state.location.search).toBe('?customer=C-1042&direction=outgoing&min=500'));
    await waitFor(() => expect(requests.at(-1)!.get('min_amount')).toBe('500'));
  });

  it('loads every page for the focused flow diagram', async () => {
    const many = Array.from({ length: 620 }, (_, index) => makeTx(index + 10));
    server.use(transactionsHandler(many));
    storeSession('admin');
    const { user } = renderApp('/transactions');
    await screen.findByText('620 eşleşen işlem · 500 gösteriliyor');
    await user.selectOptions(screen.getByLabelText('Transfer bağlantılarını göster'), 'account:TR-ACC-1042');

    expect(await screen.findByRole('img', { name: /Hesap: TR-ACC-1042 · Ahmet Yılmaz için transfer akışı/ })).toBeInTheDocument();
    expect(screen.getByText(/eşleşen 620 transferin tümü: 1 para birimi bazlı rota, 2 hesap/)).toBeInTheDocument();
    const focusRequests = requests.filter((params) => params.get('account_no') === 'TR-ACC-1042');
    expect(focusRequests.map((params) => params.get('offset'))).toEqual(['0', '500']);

    // The second toggle belongs to the flow diagram (the first is the timeline's).
    await user.click(screen.getAllByRole('button', { name: 'Tablo olarak göster' }).at(-1)!);
    expect(screen.getByRole('columnheader', { name: 'Rota' })).toBeInTheDocument();
    expect(screen.getByText('620.000,00 TRY')).toBeInTheDocument();
  }, 15_000); // Renders 500 table rows plus the diagram.

  it('shows an empty state and server validation errors', async () => {
    server.use(transactionsHandler([]));
    storeSession('admin');
    renderApp('/transactions?customer=NOPE');
    expect(await screen.findByText('Filtrelerle eşleşen işlem yok')).toBeInTheDocument();

    server.use(
      http.get(`${API}/transactions`, () =>
        HttpResponse.json({ detail: 'min_amount must not exceed max_amount.' }, { status: 422 }),
      ),
    );
    renderApp('/transactions?min=5&max=9');
    expect(await screen.findByText('min_amount must not exceed max_amount.')).toBeInTheDocument();
  });

  it('is limited to customer:view', async () => {
    storeSession('ayse.karaca');
    renderApp('/transactions');
    expect(await screen.findByText('Bu sayfaya erişim yetkiniz yok')).toBeInTheDocument();
    expect(requests).toHaveLength(0);
  });
});
