import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { apiRequest, type QueryValue } from '@/api/client';
import { accountPageSchema, customerAnalysisSchema, customerPageSchema, customerProfileSchema } from '@/api/schemas/customers';

export const CUSTOMER_PAGE_SIZE = 50;

type Query = Record<string, QueryValue>;

export const customerKeys = {
  list: (query: Query) => ['customers', 'list', query] as const,
  accounts: (query: Query) => ['customers', 'accounts', query] as const,
  profile: (customerNo: string) => ['customers', 'profile', customerNo] as const,
  analysis: (customerNo: string, days: number) => ['customers', 'analysis', customerNo, days] as const,
};

/** GET /customers — paged and searched on the server. */
export function useCustomers(query: Query) {
  return useQuery({
    queryKey: customerKeys.list(query),
    queryFn: ({ signal }) => apiRequest('/customers', { query, schema: customerPageSchema, signal }),
    placeholderData: keepPreviousData,
  });
}

/** GET /accounts — each page is written to the audit log, so no refetch on focus. */
export function useAccounts(query: Query, enabled = true) {
  return useQuery({
    queryKey: customerKeys.accounts(query),
    queryFn: ({ signal }) => apiRequest('/accounts', { query, schema: accountPageSchema, signal }),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    enabled,
  });
}

/** GET /customers/{no} — logged as a customer view (K6). */
export function useCustomerProfile(customerNo: string) {
  return useQuery({
    queryKey: customerKeys.profile(customerNo),
    queryFn: ({ signal }) =>
      apiRequest(`/customers/${encodeURIComponent(customerNo)}`, { schema: customerProfileSchema, signal }),
    enabled: customerNo.length > 0,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60_000,
  });
}

export const ANALYSIS_PERIODS = [30, 90, 180] as const;
export type AnalysisPeriod = (typeof ANALYSIS_PERIODS)[number];

/** GET /customers/{no}/analysis (E12) — logged as a customer view, so no refetch on focus. */
export function useCustomerAnalysis(customerNo: string, days: AnalysisPeriod, enabled = true) {
  return useQuery({
    queryKey: customerKeys.analysis(customerNo, days),
    queryFn: ({ signal }) =>
      apiRequest(`/customers/${encodeURIComponent(customerNo)}/analysis`, { query: { days }, schema: customerAnalysisSchema, signal }),
    enabled: enabled && customerNo.length > 0,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60_000,
  });
}
