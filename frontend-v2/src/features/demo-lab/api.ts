import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@/api/client';
import { demoRunSchema, demoStatusSchema, type DemoRun, type DemoStatus } from '@/api/schemas/demo';

export const demoKeys = {
  status: ['demo', 'status'] as const,
  /** The latest seed result, kept for this session only (like Streamlit's session state). */
  lastRun: ['demo-session', 'last-run'] as const,
};

/** GET /demo/status — requires dashboard:view. */
export function useDemoStatus() {
  return useQuery({
    queryKey: demoKeys.status,
    queryFn: ({ signal }) => apiRequest('/demo/status', { schema: demoStatusSchema, signal }),
  });
}

/** The last run lives in the query cache, so it survives navigation but not sign-out. */
export function useLastDemoRun() {
  return useQuery<DemoRun | null>({
    queryKey: demoKeys.lastRun,
    queryFn: () => null,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/** POST /demo/seed — requires upload:create and ENABLE_DEMO_ENDPOINTS=true. */
export function useSeedDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (useSavedRules: boolean) =>
      apiRequest('/demo/seed', { method: 'POST', query: { use_saved_rules: useSavedRules }, schema: demoRunSchema }),
    onSuccess: (run) => {
      queryClient.setQueryData(demoKeys.lastRun, run);
      // The seed response has no `seed_enabled`; keep the flag from the status query
      // so the page doesn't flip to the "disabled" banner after a successful seed.
      queryClient.setQueryData<DemoStatus>(demoKeys.status, (previous) => ({
        ...run,
        seed_enabled: run.seed_enabled ?? previous?.seed_enabled ?? true,
      }));
      for (const key of ['dashboard', 'alerts', 'transactions', 'admin']) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}
