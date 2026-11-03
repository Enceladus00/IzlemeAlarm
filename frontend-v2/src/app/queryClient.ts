import { QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/api/client';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Avoid surprise refetches while an analyst is mid-investigation.
        refetchOnWindowFocus: false,
        // Retry only transient failures; 4xx answers will not change on retry.
        retry: (failureCount, error) =>
          failureCount < 2 &&
          error instanceof ApiError &&
          (error.kind === 'network' || error.kind === 'unavailable'),
      },
      mutations: { retry: false },
    },
  });
}
