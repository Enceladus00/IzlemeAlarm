import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '@/api/client';
import { healthSchema, systemOverviewSchema } from '@/api/schemas/dashboard';

export const systemKeys = {
  overview: ['admin', 'system-overview'] as const,
  health: ['health'] as const,
};

/** GET /admin/system-overview — requires user:manage. */
export function useSystemOverview() {
  return useQuery({
    queryKey: systemKeys.overview,
    queryFn: ({ signal }) => apiRequest('/admin/system-overview', { schema: systemOverviewSchema, signal }),
    staleTime: 0,
  });
}

/** GET /health (public), timed in the browser to show API round-trip latency. */
export function useApiHealth() {
  return useQuery({
    queryKey: systemKeys.health,
    queryFn: async ({ signal }) => {
      const started = performance.now();
      const health = await apiRequest('/health', { schema: healthSchema, signal });
      return { ...health, latencyMs: Math.round(performance.now() - started) };
    },
    staleTime: 0,
    retry: false,
  });
}
