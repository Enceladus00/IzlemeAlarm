import { act, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { SESSION_STORAGE_KEY } from '@/auth/session';
import { LANGUAGE_STORAGE_KEY } from '@/i18n';
import { THEME_STORAGE_KEY } from '@/theme/theme-context';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

async function signIn(user: ReturnType<typeof renderApp>['user'], username: string, password = 'secret') {
  await user.type(await screen.findByLabelText('Kullanıcı adı'), username);
  await user.type(screen.getByLabelText('Parola'), password);
  await user.click(screen.getByRole('button', { name: 'Oturum aç' }));
}

async function navigation() {
  return (await screen.findAllByRole('navigation', { name: 'Ana gezinme' }))[0]!;
}

describe('authentication', () => {
  it('redirects to login, validates input, and rejects a wrong password', async () => {
    const { user } = renderApp('/alerts');
    await user.click(await screen.findByRole('button', { name: 'Oturum aç' }));
    expect(await screen.findByText('Kullanıcı adını girin.')).toBeInTheDocument();
    expect(screen.getByText('Parolayı girin.')).toBeInTheDocument();

    await signIn(user, 'admin', 'wrong');
    expect(await screen.findByText('Kullanıcı adı veya parola hatalı.')).toBeInTheDocument();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it('signs in, returns to the requested page, and shows only permitted screens', async () => {
    const { user, router } = renderApp('/alerts');
    await signIn(user, 'ayse.karaca');

    await waitFor(() => expect(router.state.location.pathname).toBe('/alerts'));
    const nav = await navigation();
    expect(within(nav).getByRole('link', { name: /Tespit özeti/ })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: /Alarm inceleme/ })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: /Demo laboratuvarı/ })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: /Kullanıcı yönetimi/ })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: /İşlem analizi/ })).not.toBeInTheDocument();
    expect(screen.getAllByText('Analist')[0]).toBeInTheDocument();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toContain('token-ayse.karaca');
  });

  it('shows a forbidden state when a screen is opened by URL without permission', async () => {
    storeSession('ayse.karaca');
    renderApp('/users');
    expect(await screen.findByText('Bu sayfaya erişim yetkiniz yok')).toBeInTheDocument();
    expect(screen.getByText(/user:manage/)).toBeInTheDocument();
  });

  it('explains when an account has no permissions', async () => {
    storeSession('nobody');
    renderApp('/');
    expect(await screen.findByText(/etkin bir uygulama yetkisi yok/)).toBeInTheDocument();
  });

  it('restores a session after refresh and signs out on request', async () => {
    storeSession('admin');
    const { user, router } = renderApp('/');
    await waitFor(() => expect(router.state.location.pathname).toBe('/my-panel'));

    await user.click(screen.getAllByRole('button', { name: 'Oturumu kapat' })[0]!);
    expect(await screen.findByText('Oturumunuz kapatıldı.')).toBeInTheDocument();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it('returns to login with an expiry message when the API rejects the token', async () => {
    storeSession('admin');
    server.use(
      http.get(`${API}/auth/me`, () =>
        HttpResponse.json({ detail: 'Invalid or expired authentication token.' }, { status: 401 }),
      ),
    );
    renderApp('/overview');
    expect(await screen.findByText(/Oturumunuzun süresi doldu/)).toBeInTheDocument();
  });

  it('signs out automatically when the token expires', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      storeSession('admin', 3_000);
      renderApp('/overview');
      expect(await screen.findAllByText(/Oturum süresi: 00:0/)).not.toHaveLength(0);
      await act(async () => {
        vi.advanceTimersByTime(3_500);
      });
      expect(await screen.findByText(/Oturumunuzun süresi doldu/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('preferences', () => {
  it('switches to English and remembers the choice', async () => {
    const { user } = renderApp('/login');
    await user.click(await screen.findByRole('button', { name: 'English' }));
    expect(await screen.findByRole('heading', { name: 'Sentinel sign in' })).toBeInTheDocument();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });

  it('toggles dark mode and remembers the choice', async () => {
    const { user } = renderApp('/login');
    await user.click(await screen.findByRole('button', { name: 'Koyu temaya geç' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(screen.getByRole('button', { name: 'Açık temaya geç' })).toBeInTheDocument();
  });
});
