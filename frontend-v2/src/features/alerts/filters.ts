import {
  ALERT_SEVERITIES,
  QUEUE_STATUSES,
  type AlertSeverity,
  type QueueStatus,
} from '@/api/schemas/alerts';
import { isoDate } from '@/utils/format';

export const DATE_RANGES = ['all', 'today', '7d', '30d', 'custom'] as const;
export type DateRange = (typeof DATE_RANGES)[number];

export const QUEUE_SORTS = ['severity_age', 'waiting'] as const;
export type QueueSort = (typeof QUEUE_SORTS)[number];

export interface QueueFilters {
  status: QueueStatus;
  severity: AlertSeverity | 'all';
  rule: string;
  range: DateRange;
  from: string;
  to: string;
  q: string;
  sort: QueueSort;
  /** Zero-based page of customers. */
  page: number;
}

/**
 * Analyst work queue: new alerts, all time. (A default date window would silently
 * hide old, still-unhandled alerts.)
 */
export const ANALYST_DEFAULTS: QueueFilters = {
  status: 'new',
  severity: 'all',
  rule: 'all',
  range: 'all',
  from: '',
  to: '',
  q: '',
  sort: 'severity_age',
  page: 0,
};

/** Compliance officers start with escalated cases, longest waiting first (API design 8.12). */
export const COMPLIANCE_DEFAULTS: QueueFilters = { ...ANALYST_DEFAULTS, status: 'in_review', sort: 'waiting' };

/** Kept for callers that do not know the role. */
export const DEFAULT_FILTERS = ANALYST_DEFAULTS;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

export function parseFilters(params: URLSearchParams, defaults: QueueFilters = ANALYST_DEFAULTS): QueueFilters {
  const page = Number(params.get('page') ?? '1');
  return {
    status: oneOf(params.get('status'), QUEUE_STATUSES, defaults.status),
    severity: oneOf(params.get('severity'), ['all', ...ALERT_SEVERITIES], 'all'),
    rule: params.get('rule')?.trim() || 'all',
    range: oneOf(params.get('range'), DATE_RANGES, 'all'),
    from: ISO_DATE.test(params.get('from') ?? '') ? params.get('from')! : '',
    to: ISO_DATE.test(params.get('to') ?? '') ? params.get('to')! : '',
    q: params.get('q') ?? '',
    sort: oneOf(params.get('sort'), QUEUE_SORTS, defaults.sort),
    page: Number.isInteger(page) && page > 1 ? page - 1 : 0,
  };
}

/** Serializes only non-default values so URLs stay short and shareable. */
export function toSearchParams(filters: QueueFilters, defaults: QueueFilters = ANALYST_DEFAULTS): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status !== defaults.status) params.set('status', filters.status);
  if (filters.severity !== 'all') params.set('severity', filters.severity);
  if (filters.rule !== 'all') params.set('rule', filters.rule);
  if (filters.range !== 'all') params.set('range', filters.range);
  if (filters.range === 'custom') {
    if (filters.from) params.set('from', filters.from);
    if (filters.to) params.set('to', filters.to);
  }
  if (filters.q.trim()) params.set('q', filters.q.trim());
  if (filters.sort !== defaults.sort) params.set('sort', filters.sort);
  if (filters.page > 0) params.set('page', String(filters.page + 1));
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

/** Query parameters for GET /alerts/queue. */
export function toApiQuery(filters: QueueFilters, today: Date, pageSize: number) {
  return {
    status: filters.status,
    severity: filters.severity === 'all' ? undefined : filters.severity,
    rule_code: filters.rule === 'all' ? undefined : filters.rule,
    q: filters.q.trim() || undefined,
    sort: filters.sort,
    offset: filters.page * pageSize,
    limit: pageSize,
    ...dateWindow(filters, today),
  };
}
