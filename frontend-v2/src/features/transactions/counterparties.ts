import type { TransactionSummary } from '@/api/schemas/transactions';
import { toCents } from './flow';

/**
 * One row per counterparty account of the focus, per currency: money in from
 * it, money out to it, and how much of that was alert-linked. Pure, so the
 * diagram and its table render the same numbers.
 */
export interface CounterpartyRow {
  account: string;
  /** Signed handle to expand this counterparty (empty when the API sent none). */
  ref: string;
  label: string;
  currency: string;
  inCents: bigint;
  outCents: bigint;
  inCount: number;
  outCount: number;
  /** Alert-linked transfers / all transfers with this counterparty. */
  flaggedShare: number;
  rules: string[];
}

export interface CounterpartyFlow {
  currencies: string[];
  rows: CounterpartyRow[];
  /** Transfers between the focus's own accounts (customer focus only). */
  internal: { currency: string; count: number; cents: bigint }[];
  /** Refs of the focus's own accounts, to recognise them in expanded neighbourhoods. */
  focusRefs: string[];
}

type Route = TransactionSummary['routes'][number];

export function buildCounterpartyFlow(routes: Route[]): CounterpartyFlow {
  const rows = new Map<string, CounterpartyRow & { flagged: number }>();
  const internal = new Map<string, { currency: string; count: number; cents: bigint }>();
  const focusRefs = new Set<string>();
  for (const route of routes) {
    if (route.sender_is_focus && route.sender_ref) focusRefs.add(route.sender_ref);
    if (route.receiver_is_focus && route.receiver_ref) focusRefs.add(route.receiver_ref);
    const cents = toCents(route.amount);
    if (route.sender_is_focus && route.receiver_is_focus) {
      const entry = internal.get(route.currency) ?? { currency: route.currency, count: 0, cents: 0n };
      entry.count += route.count;
      entry.cents += cents;
      internal.set(route.currency, entry);
      continue;
    }
    const incoming = route.receiver_is_focus;
    const account = incoming ? route.sender_account : route.receiver_account;
    const label = incoming ? route.sender_label : route.receiver_label;
    const ref = incoming ? route.sender_ref : route.receiver_ref;
    const key = `${account}|${route.currency}`;
    const row = rows.get(key) ?? {
      account,
      ref,
      label,
      currency: route.currency,
      inCents: 0n,
      outCents: 0n,
      inCount: 0,
      outCount: 0,
      flaggedShare: 0,
      flagged: 0,
      rules: [],
    };
    if (incoming) {
      row.inCents += cents;
      row.inCount += route.count;
    } else {
      row.outCents += cents;
      row.outCount += route.count;
    }
    row.flagged += route.alert_linked;
    row.rules = [...new Set([...row.rules, ...route.alert_rules])].sort();
    rows.set(key, row);
  }
  const list = [...rows.values()].map(({ flagged, ...row }) => ({
    ...row,
    flaggedShare: row.inCount + row.outCount ? flagged / (row.inCount + row.outCount) : 0,
  }));
  const total = (row: CounterpartyRow) => row.inCents + row.outCents;
  list.sort((a, b) => (total(b) > total(a) ? 1 : total(b) < total(a) ? -1 : a.account.localeCompare(b.account)));
  const currencies = [...new Set(list.map((row) => row.currency))];
  // Currency with the most money first: the default view.
  currencies.sort((a, b) => {
    const sum = (currency: string) => list.filter((row) => row.currency === currency).reduce((acc, row) => acc + total(row), 0n);
    const diff = sum(b) - sum(a);
    return diff > 0n ? 1 : diff < 0n ? -1 : a.localeCompare(b);
  });
  return { currencies, rows: list, internal: [...internal.values()], focusRefs: [...focusRefs] };
}
