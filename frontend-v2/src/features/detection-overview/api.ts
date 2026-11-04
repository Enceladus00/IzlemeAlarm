import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { apiRequest } from '@/api/client';
import { alertPageSchema } from '@/api/schemas/alerts';
import { dashboardFunnelSchema, dashboardSummarySchema, rulePerformanceSchema } from '@/api/schemas/dashboard';

export const OVERVIEW_PERIODS = [7, 30, 90] as const;
export type OverviewPeriod = (typeof OVERVIEW_PERIODS)[number];

/** Dashboard answers stay fresh for a minute; a saved decision invalidates ['dashboard']. */
const DASHBOARD_STALE_MS = 60_000;

export const dashboardKeys = {
  summary: (days: number) => ['dashboard', 'summary', days] as const,
  funnel: (days: number) => ['dashboard', 'funnel', days] as const,
  rulePerformance: (days: number) => ['dashboard', 'rule-performance', days] as const,
  latestAlerts: ['alerts', 'latest'] as const,
};

/** GET /dashboard/summary — requires dashboard:view. */
export function useDashboardSummary(days: number = 30, enabled = true) {
  return useQuery({
    enabled,
    queryKey: dashboardKeys.summary(days),
    queryFn: ({ signal }) =>
      apiRequest('/dashboard/summary', { query: { days }, schema: dashboardSummarySchema, signal }),
    staleTime: DASHBOARD_STALE_MS,
  });
}

/** GET /dashboard/funnel — loaded only when the "Alarm akışı" tab is open. */
export function useFunnel(days: number) {
  return useQuery({
    queryKey: dashboardKeys.funnel(days),
    queryFn: ({ signal }) => apiRequest('/dashboard/funnel', { query: { days }, schema: dashboardFunnelSchema, signal }),
    staleTime: DASHBOARD_STALE_MS,
  });
}

/** GET /dashboard/rule-performance — loaded only when the "Kurallar" tab is open. */
export function useRulePerformance(days: number) {
  return useQuery({
    queryKey: dashboardKeys.rulePerformance(days),
    queryFn: ({ signal }) =>
      apiRequest('/dashboard/rule-performance', { query: { days }, schema: rulePerformanceSchema, signal }),
    staleTime: DASHBOARD_STALE_MS,
  });
}

/** GET /alerts?limit=8 — requires alert:view; disabled otherwise. */
export function useLatestAlerts(enabled: boolean) {
  return useQuery({
    queryKey: dashboardKeys.latestAlerts,
    queryFn: ({ signal }) => apiRequest('/alerts', { query: { limit: 8 }, schema: alertPageSchema, signal }),
    enabled,
  });
}

/** POST /rules/evaluate — requires rule:edit. Refreshes everything alert-related. */
export function useEvaluateRules() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest('/rules/evaluate', {
        method: 'POST',
        schema: z.object({ created_alerts: z.number() }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      void queryClient.invalidateQueries({ queryKey: ['alerts'] });
      void queryClient.invalidateQueries({ queryKey: ['admin'] });
    },
  });
}
