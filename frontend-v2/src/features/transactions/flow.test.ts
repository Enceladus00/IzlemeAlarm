import { buildFlowLayout, centsToDecimal, toCents, type FlowTransaction } from './flow';

/** Same fixture helper as tests/test_transaction_flow.py. */
function tx(
  sender: string,
  senderCustomer: string,
  receiver: string,
  receiverCustomer: string,
  amount: string,
  { currency = 'TRY', alertLinked = false } = {},
): FlowTransaction {
  return {
    sender_account_no: sender,
    sender_customer_no: `C-${senderCustomer}`,
    sender_customer_name: senderCustomer,
    receiver_account_no: receiver,
    receiver_customer_no: `C-${receiverCustomer}`,
    receiver_customer_name: receiverCustomer,
    currency,
    amount,
    alert_linked: alertLinked,
  };
}

describe('buildFlowLayout (parity with tests/test_transaction_flow.py)', () => {
  it('shows only the focused customer’s routes and highlights alerts', () => {
    const layout = buildFlowLayout(
      [
        tx('ACC-1', 'Origin', 'ACC-2', 'Destination', '9500.00', { alertLinked: true }),
        tx('ACC-1', 'Origin', 'ACC-2', 'Destination', '9800.00'),
        tx('ACC-1', 'Origin', 'ACC-2', 'Destination', '125.00', { currency: 'USD' }),
        tx('ACC-3', 'Other', 'ACC-4', 'Unrelated', '300.00'),
      ],
      'customer',
      'C-Origin',
    )!;
    expect([layout.involvedAccounts, layout.routes.length]).toEqual([2, 2]);
    expect(layout.routes.flatMap((route) => route.bands)).toHaveLength(4);
    const [tryRoute, usdRoute] = layout.routes;
    expect([tryRoute!.currency, centsToDecimal(tryRoute!.amountCents), tryRoute!.flagged]).toEqual(['TRY', '19300.00', 1]);
    expect([usdRoute!.currency, centsToDecimal(usdRoute!.amountCents), usdRoute!.flagged]).toEqual(['USD', '125.00', 0]);
    expect(layout.sources.map((card) => [card.account.customerName, card.focused])).toEqual([['Origin', true]]);
    const names = [...layout.sources, ...layout.recipients].map((card) => card.account.customerName);
    expect(names).not.toContain('Unrelated');
  });

  it('keeps every link in a cycle when focusing an account', () => {
    const layout = buildFlowLayout(
      [
        tx('ACC-1', 'One', 'ACC-2', 'Two', '100.00'),
        tx('ACC-2', 'Two', 'ACC-3', 'Three', '200.00'),
        tx('ACC-3', 'Three', 'ACC-1', 'One', '300.00', { alertLinked: true }),
      ],
      'account',
      'ACC-1',
    )!;
    expect([layout.involvedAccounts, layout.routes.length]).toEqual([3, 2]);
    expect(layout.routes.flatMap((route) => route.bands)).toHaveLength(4);
  });

  it('does not truncate focused routes', () => {
    const layout = buildFlowLayout(
      Array.from({ length: 12 }, (_, index) =>
        tx('ACC-FOCUS', 'Focus', `ACC-${index + 1}`, `Counterparty ${index + 1}`, `${(index + 1) * 100}.00`),
      ),
      'customer',
      'C-Focus',
    )!;
    expect([layout.involvedAccounts, layout.routes.length]).toEqual([13, 12]);
    expect(layout.routes.flatMap((route) => route.bands)).toHaveLength(24);
    expect(layout.canvasHeight).toBe(220 + 12 * 72);
  });

  it('returns no graph for an empty set', () => {
    expect(buildFlowLayout([], 'customer', 'C-Missing')).toBeNull();
  });

  it('matches the Python geometry for a single route', () => {
    const layout = buildFlowLayout([tx('A', 'X', 'B', 'Y', '1.00')], 'account', 'A')!;
    expect(layout.canvasHeight).toBe(500);
    expect(layout.routes[0]!.ribbonWidth).toBe(20);
    expect(layout.routes[0]!.bands[0]).toBe(
      'M 218 240.0 C 278.7 240.0, 289.3 240.0, 350 240.0 L 350 260.0 C 289.3 260.0, 278.7 260.0, 218 260.0 Z',
    );
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
