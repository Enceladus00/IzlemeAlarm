import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { AppProviders } from '@/app/providers';
import { createQueryClient } from '@/app/queryClient';
import { routes } from '@/app/routes';
import { SESSION_STORAGE_KEY } from '@/auth/session';
import { tokenFor } from './server';

/** Simulates a session restored from sessionStorage (e.g. after a page refresh). */
export function storeSession(username: string, expiresInMs = 30 * 60 * 1000): void {
  sessionStorage.setItem(
    SESSION_STORAGE_KEY,
    JSON.stringify({ token: tokenFor(username), expiresAt: Date.now() + expiresInMs }),
  );
}

/** Renders the full application (providers + routes) at the given URL. */
export function renderApp(path = '/', options: { userEventOptions?: Parameters<typeof userEvent.setup>[0] } = {}) {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({
    ...queryClient.getDefaultOptions(),
    queries: { ...queryClient.getDefaultOptions().queries, retry: false },
  });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup(options.userEventOptions);
  const result = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...result, user, router, queryClient };
}
