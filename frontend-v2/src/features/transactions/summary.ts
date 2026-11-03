import type { Transaction } from '@/api/schemas/transactions';
import { isoDate, parseApiDate } from '@/utils/format';
import { toCents } from './flow';

export interface CurrencyTotal {
  currency: string;
  count: number;
  cents: bigint;
}

export interface TransferSummary {
  count: number;
  uniqueAccounts: number;
  /** Set only when a customer is selected (direction is meaningful). */
  incoming: CurrencyTotal[] | null;
  outgoing: CurrencyTotal[] | null;
  /** Set only when no customer is selected: one total per currency. */
  totals: CurrencyTotal[] | null;
}

function addTo(map: Map<string, CurrencyTotal>, tx: Transaction) {
  const entry = map.get(tx.currency) ?? { currency: tx.currency, count: 0, cents: 0n };
  entry.count += 1;
  entry.cents += toCents(tx.amount);
  map.set(tx.currency, entry);
}

const sorted = (map: Map<string, CurrencyTotal>) => [...map.values()].sort((a, b) => a.currency.localeCompare(b.currency));

/**
 * Without a customer, every transfer is both someone's incoming and someone's
 * outgoing, so a split would double count; we show one total per currency.
 */
export function summarizeTransfers(transactions: Transaction[], customerNo: string): TransferSummary {
  const accounts = new Set<string>();
  for (const tx of transactions) {
    accounts.add(tx.sender_account_no);
    accounts.add(tx.receiver_account_no);
  }
  if (!customerNo) {
    const totals = new Map<string, CurrencyTotal>();
    transactions.forEach((tx) => addTo(totals, tx));
    return { count: transactions.length, uniqueAccounts: accounts.size, incoming: null, outgoing: null, totals: sorted(totals) };
  }
  const incoming = new Map<string, CurrencyTotal>();
  const outgoing = new Map<string, CurrencyTotal>();
  for (const tx of transactions) {
    if (tx.receiver_customer_no === customerNo) addTo(incoming, tx);
    if (tx.sender_customer_no === customerNo) addTo(outgoing, tx);
  }
  return {
    count: transactions.length,
    uniqueAccounts: accounts.size,
    incoming: sorted(incoming),
    outgoing: sorted(outgoing),
    totals: null,
  };
}

export interface TimelineBucket {
  date: string;
  count: number;
}

const DAILY_LIMIT_DAYS = 120;

/** Contiguous daily counts (gaps filled with 0); weekly buckets for long spans. */
export function activityTimeline(transactions: Transaction[]): { granularity: 'day' | 'week'; buckets: TimelineBucket[] } {
  const days = transactions
    .map((tx) => parseApiDate(tx.tx_time))
    .filter((date): date is Date => date !== null)
    .map((date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()));
  if (days.length === 0) return { granularity: 'day', buckets: [] };

  const first = new Date(Math.min(...days.map((d) => d.getTime())));
  const last = new Date(Math.max(...days.map((d) => d.getTime())));
  const spanDays = Math.round((last.getTime() - first.getTime()) / 86_400_000) + 1;
  const granularity = spanDays > DAILY_LIMIT_DAYS ? 'week' : 'day';

  const bucketStart = (date: Date) => {
    if (granularity === 'day') return date;
    const monday = new Date(date);
    monday.setDate(date.getDate() - ((date.getDay() + 6) % 7));
    return monday;
  };

  const counts = new Map<string, number>();
  for (const day of days) {
    const key = isoDate(bucketStart(day));
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  const buckets: TimelineBucket[] = [];
  const cursor = bucketStart(first);
  const end = bucketStart(last);
  while (cursor.getTime() <= end.getTime()) {
    const key = isoDate(cursor);
    buckets.push({ date: key, count: counts.get(key) ?? 0 });
    cursor.setDate(cursor.getDate() + (granularity === 'day' ? 1 : 7));
  }
  return { granularity, buckets };
}

export interface FocusOption {
  type: 'customer' | 'account';
  id: string;
  name: string;
}

/** Customers and accounts that appear in the loaded transfers, for the focus picker. */
export function focusOptions(transactions: Transaction[]): FocusOption[] {
  const seen = new Map<string, FocusOption>();
  const add = (option: FocusOption) => seen.set(`${option.type}:${option.id}`, option);
  for (const tx of transactions) {
    add({ type: 'customer', id: tx.sender_customer_no, name: tx.sender_customer_name });
    add({ type: 'customer', id: tx.receiver_customer_no, name: tx.receiver_customer_name });
    add({ type: 'account', id: tx.sender_account_no, name: tx.sender_customer_name });
    add({ type: 'account', id: tx.receiver_account_no, name: tx.receiver_customer_name });
  }
  return [...seen.values()].sort(
    (a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name, 'tr') || a.id.localeCompare(b.id),
  );
}
