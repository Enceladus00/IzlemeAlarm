import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { apiRequest } from '@/api/client';
import { alertPageSchema } from '@/api/schemas/alerts';
import { dashboardSummarySchema } from '@/api/schemas/dashboard';

export const dashboardKeys = {
  summary: ['dashboard', 'summary'] as const,
  latestAlerts: ['alerts', 'latest'] as const,
};

/** GET /dashboard/summary — requires dashboard:view. */
export function useDashboardSummary() {
  return useQuery({
    queryKey: dashboardKeys.summary,
    queryFn: ({ signal }) => apiRequest('/dashboard/summary', { schema: dashboardSummarySchema, signal }),
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
