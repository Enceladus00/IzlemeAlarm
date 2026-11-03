import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest, type QueryValue } from '@/api/client';
import {
  alertDetailSchema,
  alertPageSchema,
  alertStatusResultSchema,
  compareRuleCodes,
  ruleCodesSchema,
  type AlertStatus,
} from '@/api/schemas/alerts';
import { customerHistorySchema } from '@/api/schemas/transactions';

/** The API caps GET /alerts at 200 per request. */
export const QUEUE_PAGE_SIZE = 200;

type AlertQuery = Record<string, QueryValue>;

export const alertKeys = {
  all: ['alerts'] as const,
  queue: (query: AlertQuery) => ['alerts', 'queue', query] as const,
  count: (query: AlertQuery) => ['alerts', 'count', query] as const,
  ruleCodes: ['alerts', 'rule-codes'] as const,
  detail: (id: number) => ['alerts', 'detail', id] as const,
  customer: (customerNo: string) => ['alerts', 'customer', customerNo] as const,
  customerHistory: (id: number) => ['alerts', 'customer-history', id] as const,
};

/** GET /alerts in pages of 200; `fetchNextPage` appends the next offset. */
export function useAlertQueue(query: AlertQuery, enabled = true) {
  return useInfiniteQuery({
    queryKey: alertKeys.queue(query),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      apiRequest('/alerts', {
        query: { ...query, offset: pageParam, limit: QUEUE_PAGE_SIZE },
        schema: alertPageSchema,
        signal,
      }),
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((sum, page) => sum + page.items.length, 0);
      return loaded < last.total && last.items.length > 0 ? loaded : undefined;
    },
    enabled,
  });
}

/** Total number of alerts matching a filter (one-row request). */
export function useAlertCount(query: AlertQuery, enabled = true) {
  return useQuery({
    queryKey: alertKeys.count(query),
    queryFn: ({ signal }) =>
      apiRequest('/alerts', { query: { ...query, limit: 1 }, schema: alertPageSchema, signal }).then((page) => page.total),
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

/** Every alert raised for one customer, any status (newest first). */
export function useCustomerAlerts(customerNo: string | undefined) {
  return useQuery({
    queryKey: alertKeys.customer(customerNo ?? ''),
    queryFn: ({ signal }) =>
      apiRequest('/alerts', {
        query: { customer_no: customerNo, limit: QUEUE_PAGE_SIZE },
        schema: alertPageSchema,
        signal,
      }),
    enabled: !!customerNo,
  });
}

/** Alert-scoped customer history (allowed with alert:view alone). */
export function useAlertCustomerHistory(alertId: number, enabled: boolean) {
  return useQuery({
    queryKey: alertKeys.customerHistory(alertId),
    queryFn: ({ signal }) =>
      apiRequest(`/alerts/${alertId}/customer-transactions`, {
        query: { limit: 200 },
        schema: customerHistorySchema,
        signal,
      }),
    enabled,
  });
}

export function useUpdateAlertStatus(alertId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { status: AlertStatus; note: string | null }) =>
      apiRequest(`/alerts/${alertId}/status`, { method: 'PATCH', json: body, schema: alertStatusResultSchema }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: alertKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}
