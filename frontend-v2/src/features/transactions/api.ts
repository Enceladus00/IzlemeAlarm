import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { apiRequest, type QueryValue } from '@/api/client';
import { transactionPageSchema, type Transaction } from '@/api/schemas/transactions';

/** The API caps GET /transactions at 500 per request. */
export const TX_PAGE_SIZE = 500;
/** Safety cap for the focused flow diagram (Streamlit had none). */
export const FOCUS_MAX_PAGES = 20;

type TxQuery = Record<string, QueryValue>;

export const txKeys = {
  list: (query: TxQuery) => ['transactions', 'list', query] as const,
  focus: (query: TxQuery) => ['transactions', 'focus', query] as const,
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
 * Every transfer for one customer or account (all pages), like Streamlit's
 * account-movement view, capped at FOCUS_MAX_PAGES pages.
 */
export function useFocusedTransfers(query: TxQuery | null) {
  return useQuery({
    queryKey: txKeys.focus(query ?? {}),
    enabled: query !== null,
    queryFn: async ({ signal }) => {
      const items: Transaction[] = [];
      let total = 0;
      for (let page = 0; page < FOCUS_MAX_PAGES; page += 1) {
        const result = await apiRequest('/transactions', {
          query: { ...query, offset: items.length, limit: TX_PAGE_SIZE },
          schema: transactionPageSchema,
          signal,
        });
        total = result.total;
        items.push(...result.items);
        if (items.length >= total || result.items.length === 0) break;
      }
      return { items, total, capped: items.length < total };
    },
  });
}
