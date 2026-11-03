import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { DemoRun, DemoStatus } from '@/api/schemas/demo';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const status: DemoStatus = {
  seeded: true,
  fixture_ready: true,
  customers: 2,
  accounts: 2,
  transactions: 1,
  customer_rows: [
    { customer_no: 'DEMO-001', full_name: 'Demo Customer 01', customer_type: 'BIREYSEL', monthly_income: '50000.00', account_count: 1, is_active: true },
    { customer_no: 'DEMO-002', full_name: 'Demo Customer 02', customer_type: 'KURUMSAL', monthly_income: null, account_count: 1, is_active: true },
  ],
  account_rows: [
    { account_no: 'DEMO-ACC-001', customer_no: 'DEMO-001', currency: 'TRY', account_type: 'current', opened_at: '2025-11-02', is_active: true },
    { account_no: 'DEMO-ACC-002', customer_no: 'DEMO-002', currency: 'TRY', account_type: null, opened_at: null, is_active: false },
  ],
  transaction_rows: [
    {
      transaction_no: 'D-R01-001',
      sender_customer_no: 'DEMO-001',
      sender_account_no: 'DEMO-ACC-001',
      receiver_customer_no: 'DEMO-002',
      receiver_account_no: 'DEMO-ACC-002',
      amount: '9800.00',
      currency: 'TRY',
      tx_time: '2026-11-02T16:05:28.142507',
      channel: 'internet',
      is_active: true,
    },
  ],
  scenarios: [
    { rule_code: 'R01', customer_no: 'DEMO-001', account_no: 'DEMO-ACC-001', intent: 'Repeated transfers just below the configured limit.', expected_signal: 'score >= 0.50' },
  ],
  seed_enabled: true,
};

const run: DemoRun = {
  ...status,
  run_id: 'run-123',
  created_alerts: 5,
  parameter_mode: 'saved_active_rules',
  rule_summary: { R01: { evaluated: 24, alerts: 1, skipped_unset: { KURUMSAL: 3 }, elapsed_ms: 12.5 } },
  scenarios: [
    {
      ...status.scenarios[0]!,
      result_status: 'evaluated',
      score: '0.8750',
      evidence_transactions: 2,
      evidence_transaction_numbers: ['D-R01-001', 'D-R01-002'],
      observed_signal: true,
      passed: true,
    },
  ],
};

let seedCalls: string[] = [];

beforeEach(() => {
  seedCalls = [];
  server.use(
    http.get(`${API}/demo/status`, () => HttpResponse.json(status)),
    http.post(`${API}/demo/seed`, ({ request }) => {
      seedCalls.push(new URL(request.url).searchParams.get('use_saved_rules') ?? '');
      return HttpResponse.json(run);
    }),
  );
});

describe('Demo lab', () => {
  it('shows the stored fixture before any run', async () => {
    storeSession('admin');
    renderApp('/demo');
    expect(await screen.findByText(/Veri seti kayıtları aşağıda/)).toBeInTheDocument();
    const coverage = screen.getByRole('table', { name: 'Kural kapsamı' });
    expect(within(coverage).getByText('çalıştırılmadı')).toBeInTheDocument();
    expect(within(coverage).getByText('Repeated transfers just below the configured limit.')).toBeInTheDocument();
  });

  it('seeds with saved rules and shows scores, evidence and rule execution', async () => {
    storeSession('admin');
    const { user } = renderApp('/demo');
    await user.click(await screen.findByLabelText(/Kayıtlı etkin kuralları ve eşikleri kullan/));
    await user.click(screen.getByRole('button', { name: 'Demo veriyi oluştur ve değerlendir' }));

    expect(await screen.findByText('Demo hazır: 2 müşteri, 2 hesap, 1 işlem.')).toBeInTheDocument();
    expect(seedCalls).toEqual(['true']);
    expect(screen.getByText('Son çalıştırma: run-123 · mod: kayıtlı etkin kurallar · 5 yeni alarm')).toBeInTheDocument();
    const coverage = screen.getByRole('table', { name: 'Kural kapsamı' });
    expect(within(coverage).getByText('0,875')).toBeInTheDocument();
    expect(within(coverage).getByText('D-R01-001, D-R01-002')).toBeInTheDocument();
    const execution = screen.getByRole('table', { name: 'Kural çalıştırma' });
    expect(within(execution).getByText('24')).toBeInTheDocument();
    expect(within(execution).getByText('3')).toBeInTheDocument();
    expect(within(execution).getByText('12,5')).toBeInTheDocument();
  });

  it('browses customers, accounts and transactions with keyboard tabs', async () => {
    storeSession('admin');
    const { user } = renderApp('/demo');
    const coverageTab = await screen.findByRole('tab', { name: 'Kural kapsamı' });
    coverageTab.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Müşteriler' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Müşteriler' })).toHaveFocus();
    expect(within(screen.getByRole('tabpanel')).getByText('50.000,00')).toBeInTheDocument();

    await user.keyboard('{End}');
    expect(within(screen.getByRole('tabpanel')).getByText('9.800,00 TRY')).toBeInTheDocument();
    await user.keyboard('{ArrowLeft}');
    expect(within(screen.getByRole('tabpanel')).getByText('DEMO-ACC-002')).toBeInTheDocument();
  });

  it('explains when seeding is disabled or not permitted', async () => {
    server.use(http.get(`${API}/demo/status`, () => HttpResponse.json({ ...status, seed_enabled: false })));
    storeSession('admin');
    renderApp('/demo');
    expect(await screen.findByText('Demo verisi oluşturma kapalı')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Demo veriyi oluştur ve değerlendir' })).not.toBeInTheDocument();
  });

  it('lets an analyst inspect but not seed', async () => {
    storeSession('ayse.karaca');
    renderApp('/demo');
    expect(await screen.findByText(/rolünüz veri oluşturamaz/)).toBeInTheDocument();
  });

  it('explains an empty fixture', async () => {
    server.use(
      http.get(`${API}/demo/status`, () =>
        HttpResponse.json({ ...status, seeded: false, customers: 0, customer_rows: [], account_rows: [], transaction_rows: [] }),
      ),
    );
    storeSession('admin');
    renderApp('/demo');
    expect(await screen.findByText(/Kayıtlı demo veri seti yok/)).toBeInTheDocument();
  });
});
