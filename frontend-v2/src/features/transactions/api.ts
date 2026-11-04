import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { apiRequest, type QueryValue } from '@/api/client';
import { transactionPageSchema, transactionSummarySchema } from '@/api/schemas/transactions';

/** The API caps GET /transactions at 500 per request. */
export const TX_PAGE_SIZE = 500;

type TxQuery = Record<string, QueryValue>;

export const txKeys = {
  list: (query: TxQuery) => ['transactions', 'list', query] as const,
  summary: (query: TxQuery) => ['transactions', 'summary', query] as const,
};

export function useTransactions(query: TxQuery, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: txKeys.list(query),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      apiRequest('/transactions', {
        query: { ...query, offset: pageParam, limit: TX_PAGE_SIZE },
        schema: transactionPageSchema,
        signal,
      }),
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((sum, page) => sum + page.items.length, 0);
      return loaded < last.total && last.items.length > 0 ? loaded : undefined;
    },
    enabled,
  });
}

/**
 * K12: summary boxes, timeline and flow routes for every matching transfer,
 * computed on the server in one request (no transfer rows or names are sent).
 */
export function useTransactionSummary(query: TxQuery | null) {
  return useQuery({
    queryKey: txKeys.summary(query ?? {}),
    enabled: query !== null,
    queryFn: ({ signal }) => apiRequest('/transactions/summary', { query: query ?? {}, schema: transactionSummarySchema, signal }),
  });
}
