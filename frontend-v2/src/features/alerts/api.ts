import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest, type QueryValue } from '@/api/client';
import {
  alertDetailSchema,
  alertPageSchema,
  alertPageWithCountsSchema,
  alertQueueSchema,
  compareRuleCodes,
  customerContextSchema,
  decisionResultSchema,
  ruleCodesSchema,
  type AlertStatus,
} from '@/api/schemas/alerts';
import { mySummarySchema } from '@/api/schemas/dashboard';

/** Customers per queue page (the API allows up to 200). */
export const QUEUE_PAGE_SIZE = 50;
/** GET /alerts caps one request at 200 alerts. */
const ALERT_LIST_LIMIT = 200;

type AlertQuery = Record<string, QueryValue>;

export const alertKeys = {
  all: ['alerts'] as const,
  queue: (query: AlertQuery) => ['alerts', 'queue', query] as const,
  ruleCodes: ['alerts', 'rule-codes'] as const,
  detail: (id: number) => ['alerts', 'detail', id] as const,
  customer: (customerNo: string, status?: string) => ['alerts', 'customer', customerNo, status ?? 'all'] as const,
  customerContext: (id: number) => ['alerts', 'customer-context', id] as const,
  list: (query: AlertQuery) => ['alerts', 'list', query] as const,
};

/** Alerts per page on the "Tüm alarmlar" screen (E11). */
export const ALL_ALERTS_PAGE_SIZE = 25;

/** GET /alerts with per-status counts (E11) — every status, filtered and paged on the server. */
export function useAlertList(query: AlertQuery) {
  return useQuery({
    queryKey: alertKeys.list(query),
    queryFn: ({ signal }) =>
      apiRequest('/alerts', { query: { ...query, include_counts: true }, schema: alertPageWithCountsSchema, signal }),
    placeholderData: keepPreviousData,
  });
}

/** GET /alerts/queue: customers grouped, sorted, searched and paged on the server (K1). */
export function useAlertQueue(query: AlertQuery, enabled = true) {
  return useQuery({
    queryKey: alertKeys.queue(query),
    queryFn: ({ signal }) => apiRequest('/alerts/queue', { query, schema: alertQueueSchema, signal }),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useRuleCodes() {
  return useQuery({
    queryKey: alertKeys.ruleCodes,
    queryFn: ({ signal }) =>
      apiRequest('/alerts/rule-codes', { schema: ruleCodesSchema, signal }).then((codes) => [...codes].sort(compareRuleCodes)),
    staleTime: 5 * 60_000,
  });
}

export function useAlertDetail(alertId: number) {
  return useQuery({
    queryKey: alertKeys.detail(alertId),
    queryFn: ({ signal }) => apiRequest(`/alerts/${alertId}`, { schema: alertDetailSchema, signal }),
    enabled: Number.isInteger(alertId) && alertId > 0,
  });
}

/** One customer's alerts (newest first), optionally only one status. */
export function useCustomerAlerts(customerNo: string | undefined, status?: AlertStatus, enabled = true) {
  return useQuery({
    queryKey: alertKeys.customer(customerNo ?? '', status),
    queryFn: ({ signal }) =>
      apiRequest('/alerts', {
        query: { customer_no: customerNo, status, limit: ALERT_LIST_LIMIT },
        schema: alertPageSchema,
        signal,
      }),
    enabled: !!customerNo && enabled,
  });
}

/**
 * Masked customer profile and last-6-month activity (K4). Each successful call is
 * written to the audit log as a customer view (K6), so it is loaded only on request
 * and not refetched on window focus.
 */
export function useCustomerContext(alertId: number, enabled: boolean) {
  return useQuery({
    queryKey: alertKeys.customerContext(alertId),
    queryFn: ({ signal }) =>
      apiRequest(`/alerts/${alertId}/customer-context`, { schema: customerContextSchema, signal }),
    enabled,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60_000,
  });
}

/** POST /alerts/decisions: one atomic decision for one customer's alerts (K2). */
export function useAlertDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { alert_ids: number[]; status: AlertStatus; note: string }) =>
      apiRequest('/alerts/decisions', { method: 'POST', json: body, schema: decisionResultSchema }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: alertKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

/** Number of open alerts in one queue status (summary of a one-row queue page). */
export function useAlertCount(status: 'new' | 'in_review', enabled = true) {
  return useQuery({
    queryKey: alertKeys.queue({ status, limit: 1, count: true }),
    queryFn: ({ signal }) =>
      apiRequest('/alerts/queue', { query: { status, limit: 1 }, schema: alertQueueSchema, signal }).then(
        (page) => page.summary.alerts,
      ),
    enabled,
  });
}

/** GET /dashboard/my-summary: the signed-in user's own work only. */
export function useMySummary() {
  return useQuery({
    queryKey: ['dashboard', 'my-summary'],
    queryFn: ({ signal }) => apiRequest('/dashboard/my-summary', { schema: mySummarySchema, signal }),
    staleTime: 60_000,
  });
}
