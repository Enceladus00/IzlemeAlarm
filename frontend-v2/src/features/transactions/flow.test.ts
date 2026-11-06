import { buildCounterpartyFlow } from './counterparties';
import { centsToDecimal, toCents } from './flow';

const route = (overrides: Partial<Parameters<typeof buildCounterpartyFlow>[0][number]>) => ({
  sender_account: 'TR…0001',
  receiver_account: 'TR…0002',
  sender_is_focus: true,
  receiver_is_focus: false,
  currency: 'TRY',
  count: 1,
  amount: '100.00',
  alert_linked: 0,
  sender_ref: '1.a',
  receiver_ref: '2.b',
  sender_label: 'A. Focus',
  receiver_label: 'B. Other',
  alert_rules: [],
  ...overrides,
});

describe('buildCounterpartyFlow', () => {
  it('puts money in and out with the same counterparty on one row', () => {
    const flow = buildCounterpartyFlow([
      route({ amount: '500.00', count: 2, alert_linked: 1, alert_rules: ['R14'] }),
      route({
        sender_account: 'TR…0002',
        receiver_account: 'TR…0001',
        sender_is_focus: false,
        receiver_is_focus: true,
        sender_label: 'B. Other',
        amount: '450.00',
        alert_rules: ['R10'],
      }),
    ]);
    expect(flow.rows).toHaveLength(1);
    const [row] = flow.rows;
    expect(row).toMatchObject({ account: 'TR…0002', label: 'B. Other', inCount: 1, outCount: 2, rules: ['R10', 'R14'] });
    expect(centsToDecimal(row!.inCents)).toBe('450.00');
    expect(centsToDecimal(row!.outCents)).toBe('500.00');
    expect(row!.flaggedShare).toBeCloseTo(1 / 3);
  });

  it('sorts by amount, keeps currencies apart and separates internal transfers', () => {
    const flow = buildCounterpartyFlow([
      route({ receiver_account: 'TR…0003', amount: '50.00', count: 9 }),
      route({ receiver_account: 'TR…0004', amount: '900.00', count: 1 }),
      route({ receiver_account: 'TR…0005', currency: 'USD', amount: '10.00' }),
      route({ receiver_account: 'TR…0009', receiver_is_focus: true, amount: '70.00' }),
    ]);
    expect(flow.rows.filter((row) => row.currency === 'TRY').map((row) => row.account)).toEqual(['TR…0004', 'TR…0003']);
    expect(flow.currencies).toEqual(['TRY', 'USD']);
    expect(flow.internal).toEqual([{ currency: 'TRY', count: 1, cents: 7000n }]);
  });
});

describe('exact decimal arithmetic', () => {
  it('sums amounts in cents without float drift', () => {
    const total = ['0.10', '0.20', '9999999999999.99'].reduce((sum, value) => sum + toCents(value), 0n);
    expect(centsToDecimal(total)).toBe('10000000000000.29');
    expect(toCents('125.5')).toBe(12550n);
    expect(toCents('-3')).toBe(-300n);
  });
});
