import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@/api/client';
import { rolesSchema, userSchema, usersSchema } from '@/api/schemas/users';

export const userKeys = { list: ['users', 'list'] as const, roles: ['users', 'roles'] as const };

const invalidate = (queryClient: ReturnType<typeof useQueryClient>) => {
  void queryClient.invalidateQueries({ queryKey: ['users'] });
  void queryClient.invalidateQueries({ queryKey: ['admin'] });
  void queryClient.invalidateQueries({ queryKey: ['audit'] });
};

/** GET /users — requires user:manage. */
export function useUsers(enabled = true) {
  return useQuery({
    queryKey: userKeys.list,
    queryFn: ({ signal }) => apiRequest('/users', { schema: usersSchema, signal }),
    enabled,
  });
}

/** GET /users/roles — active roles only. */
export function useRoles() {
  return useQuery({
    queryKey: userKeys.roles,
    queryFn: ({ signal }) => apiRequest('/users/roles', { schema: rolesSchema, signal }),
    staleTime: 5 * 60_000,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; password: string; role_code: string }) =>
      apiRequest('/users', { method: 'POST', json: body, schema: userSchema }),
    onSuccess: () => invalidate(queryClient),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, body }: { userId: number; body: { role_code?: string; is_active?: boolean } }) =>
      apiRequest(`/users/${userId}`, { method: 'PATCH', json: body, schema: userSchema }),
    onSuccess: () => invalidate(queryClient),
  });
}
