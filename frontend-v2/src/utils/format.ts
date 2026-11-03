import { localeFor } from '@/i18n';

/**
 * The API returns timestamps without a timezone (server-local wall time).
 * We display them exactly as recorded instead of letting the browser shift them.
 */
const NAIVE_DATETIME = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/;

export function parseApiDate(value: string): Date | null {
  const match = NAIVE_DATETIME.exec(value);
  if (!match) return null;
  const [, y, mo, d, h = '0', mi = '0', s = '0'] = match;
  return new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s));
}

export function formatDateTime(value: string | null | undefined, language: string): string {
  if (!value) return '—';
  const date = parseApiDate(value);
  if (!date) return value;
  return new Intl.DateTimeFormat(localeFor(language), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatDate(value: string | null | undefined, language: string): string {
  if (!value) return '—';
  const date = parseApiDate(value);
  if (!date) return value;
  return new Intl.DateTimeFormat(localeFor(language), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

export function formatNumber(
  value: number | string | null | undefined,
  language: string,
  options: Intl.NumberFormatOptions = {},
): string {
  if (value === null || value === undefined || value === '') return '—';
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return new Intl.NumberFormat(localeFor(language), options).format(numeric);
}

/** Amount with two decimals followed by the ISO currency code (no FX conversion). */
export function formatMoney(
  value: number | string | null | undefined,
  currency: string,
  language: string,
): string {
  const amount = formatNumber(value, language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return amount === '—' ? amount : `${amount} ${currency}`;
}

/** Local calendar date as YYYY-MM-DD (what the API's date filters expect). */
export function isoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
