import {
  ALERT_SEVERITIES,
  ALERT_STATUSES,
  type AlertSeverity,
  type AlertStatus,
} from '@/api/schemas/alerts';
import { isoDate } from '@/utils/format';

export const DATE_RANGES = ['all', 'today', '7d', '30d', 'custom'] as const;
export type DateRange = (typeof DATE_RANGES)[number];

export interface QueueFilters {
  status: AlertStatus | 'all';
  severity: AlertSeverity | 'all';
  rule: string;
  range: DateRange;
  from: string;
  to: string;
  q: string;
}

/**
 * Default view is the analyst work queue: new alerts, all time. (A default
 * date window would silently hide old, still-unhandled alerts.)
 */
export const DEFAULT_FILTERS: QueueFilters = {
  status: 'new',
  severity: 'all',
  rule: 'all',
  range: 'all',
  from: '',
  to: '',
  q: '',
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

export function parseFilters(params: URLSearchParams): QueueFilters {
  return {
    status: oneOf(params.get('status'), ['all', ...ALERT_STATUSES], DEFAULT_FILTERS.status),
    severity: oneOf(params.get('severity'), ['all', ...ALERT_SEVERITIES], 'all'),
    rule: params.get('rule')?.trim() || 'all',
    range: oneOf(params.get('range'), DATE_RANGES, 'all'),
    from: ISO_DATE.test(params.get('from') ?? '') ? params.get('from')! : '',
    to: ISO_DATE.test(params.get('to') ?? '') ? params.get('to')! : '',
    q: params.get('q') ?? '',
  };
}

/** Serializes only non-default values so URLs stay short and shareable. */
export function toSearchParams(filters: QueueFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status !== DEFAULT_FILTERS.status) params.set('status', filters.status);
  if (filters.severity !== 'all') params.set('severity', filters.severity);
  if (filters.rule !== 'all') params.set('rule', filters.rule);
  if (filters.range !== 'all') params.set('range', filters.range);
  if (filters.range === 'custom') {
    if (filters.from) params.set('from', filters.from);
    if (filters.to) params.set('to', filters.to);
  }
  if (filters.q.trim()) params.set('q', filters.q.trim());
  return params;
}


function daysAgo(today: Date, days: number): string {
  const date = new Date(today);
  date.setDate(today.getDate() - days);
  return isoDate(date);
}

/** The created_at window (inclusive dates) for a preset, relative to `today`. */
export function dateWindow(filters: QueueFilters, today: Date): { date_from?: string; date_to?: string } {
  switch (filters.range) {
    case 'today':
      return { date_from: isoDate(today) };
    case '7d':
      return { date_from: daysAgo(today, 6) };
    case '30d':
      return { date_from: daysAgo(today, 29) };
    case 'custom':
      return { date_from: filters.from || undefined, date_to: filters.to || undefined };
    default:
      return {};
  }
}

export function hasInvalidRange(filters: QueueFilters): boolean {
  return filters.range === 'custom' && !!filters.from && !!filters.to && filters.from > filters.to;
}

/** Query parameters for GET /alerts (the API accepts one value per filter). */
export function toApiQuery(filters: QueueFilters, today: Date) {
  return {
    status: filters.status === 'all' ? undefined : filters.status,
    severity: filters.severity === 'all' ? undefined : filters.severity,
    rule_code: filters.rule === 'all' ? undefined : filters.rule,
    ...dateWindow(filters, today),
  };
}
