import type { Transaction } from '@/api/schemas/transactions';
import { sampleTransaction } from '@/test/alertData';
import { centsToDecimal } from './flow';
import { parseTxFilters, toTxQuery, txFiltersToParams, validateTxFilters, EMPTY_TX_FILTERS } from './filters';
import { activityTimeline, focusOptions, summarizeTransfers } from './summary';

const tx = (partial: Partial<Transaction>): Transaction => ({ ...sampleTransaction, ...partial });

const rows = [
  tx({ transaction_id: 1, amount: '100.10', currency: 'TRY', tx_time: '2026-10-01T09:00:00' }),
  tx({ transaction_id: 2, amount: '0.20', currency: 'TRY', tx_time: '2026-10-03T09:00:00', sender_customer_no: 'C-0311', receiver_customer_no: 'C-1042', sender_account_no: 'TR-ACC-0311', receiver_account_no: 'TR-ACC-1042' }),
  tx({ transaction_id: 3, amount: '50.00', currency: 'USD', tx_time: '2026-10-03T18:00:00' }),
];

describe('summarizeTransfers', () => {
  it('splits incoming and outgoing per currency for a customer', () => {
    const summary = summarizeTransfers(rows, 'C-1042');
    expect(summary.totals).toBeNull();
    expect(summary.outgoing!.map((row) => [row.currency, centsToDecimal(row.cents), row.count])).toEqual([
      ['TRY', '100.10', 1],
      ['USD', '50.00', 1],
    ]);
    expect(summary.incoming!.map((row) => [row.currency, centsToDecimal(row.cents)])).toEqual([['TRY', '0.20']]);
    expect(summary.uniqueAccounts).toBe(2);
  });

  it('shows one total per currency without a customer (no double counting)', () => {
    const summary = summarizeTransfers(rows, '');
    expect(summary.incoming).toBeNull();
    expect(summary.totals!.map((row) => [row.currency, centsToDecimal(row.cents), row.count])).toEqual([
      ['TRY', '100.30', 2],
      ['USD', '50.00', 1],
    ]);
  });
});

describe('activityTimeline', () => {
  it('fills gaps between days with zero', () => {
    expect(activityTimeline(rows)).toEqual({
      granularity: 'day',
      buckets: [
        { date: '2026-10-01', count: 1 },
        { date: '2026-10-02', count: 0 },
        { date: '2026-10-03', count: 2 },
      ],
    });
  });

  it('switches to weeks starting Monday for long spans', () => {
    const timeline = activityTimeline([tx({ tx_time: '2026-01-07T10:00:00' }), tx({ tx_time: '2026-06-03T10:00:00' })]);
    expect(timeline.granularity).toBe('week');
    expect(timeline.buckets[0]).toEqual({ date: '2026-01-05', count: 1 });
    expect(timeline.buckets.at(-1)).toEqual({ date: '2026-06-01', count: 1 });
  });
});

describe('focus options and filters', () => {
  it('lists each customer and account once', () => {
    const options = focusOptions(rows);
    expect(options.filter((option) => option.type === 'customer').map((option) => option.id)).toEqual(['C-1042', 'C-0311']);
    expect(options.filter((option) => option.type === 'account')).toHaveLength(2);
  });

  it('validates like the API', () => {
    expect(validateTxFilters({ ...EMPTY_TX_FILTERS, direction: 'incoming' })).toEqual({ direction: 'errorDirection' });
    expect(validateTxFilters({ ...EMPTY_TX_FILTERS, min: '0' })).toEqual({ min: 'errorAmountPositive' });
    expect(validateTxFilters({ ...EMPTY_TX_FILTERS, min: '500', max: '100' })).toEqual({ max: 'errorAmountOrder' });
    expect(validateTxFilters({ ...EMPTY_TX_FILTERS, from: '2026-10-05', to: '2026-10-01' })).toEqual({ to: 'errorDateOrder' });
  });

  it('maps URL filters to API parameters', () => {
    const filters = parseTxFilters(new URLSearchParams('customer=C-1042&direction=outgoing&min=100&from=2026-10-01'));
    expect(toTxQuery(filters)).toEqual({
      customer_no: 'C-1042',
      direction: 'outgoing',
      date_from: '2026-10-01',
      date_to: undefined,
      min_amount: '100',
      max_amount: undefined,
    });
    expect(txFiltersToParams(filters, 'account:TR-1').toString()).toBe(
      'customer=C-1042&direction=outgoing&from=2026-10-01&min=100&focus=account%3ATR-1',
    );
  });
});
