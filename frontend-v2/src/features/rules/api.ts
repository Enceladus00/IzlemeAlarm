import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@/api/client';
import { ruleUpdateResultSchema, rulesSchema, type RuleUpdate } from '@/api/schemas/rules';

export const ruleKeys = { all: ['rules'] as const };

/** GET /rules — requires rule:view. */
export function useRules() {
  return useQuery({
    queryKey: ruleKeys.all,
    queryFn: ({ signal }) => apiRequest('/rules', { schema: rulesSchema, signal }),
  });
}

/** PUT /rules/{code} — requires rule:edit. */
export function useUpdateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ code, body }: { code: string; body: RuleUpdate }) =>
      apiRequest(`/rules/${encodeURIComponent(code)}`, { method: 'PUT', json: body, schema: ruleUpdateResultSchema }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ruleKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['admin'] });
    },
  });
}
