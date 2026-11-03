import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError, apiRequest, configureApiClient } from '@/api/client';
import { profileSchema, tokenResponseSchema, type Profile } from '@/api/schemas/auth';
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
  type SignOutReason,
} from './auth-context';
import type { Permission } from './permissions';
import { clearStoredSession, readStoredSession, writeStoredSession, type StoredSession } from './session';

function fetchProfile(handleUnauthorized: boolean): Promise<Profile> {
  return apiRequest('/auth/me', { schema: profileSchema, handleUnauthorized });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<StoredSession | null>(() => readStoredSession());
  const [profile, setProfile] = useState<Profile | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() => (session ? 'checking' : 'anonymous'));
  const [signOutReason, setSignOutReason] = useState<SignOutReason | null>(null);
  const [profileError, setProfileError] = useState<ApiError | null>(null);
  const tokenRef = useRef<string | null>(session?.token ?? null);

  const endSession = useCallback(
    (reason: SignOutReason) => {
      if (tokenRef.current === null && reason === 'expired') return;
      tokenRef.current = null;
      clearStoredSession();
      setSession(null);
      setProfile(null);
      setProfileError(null);
      setStatus('anonymous');
      setSignOutReason(reason);
      queryClient.cancelQueries();
      queryClient.clear();
    },
    [queryClient],
  );

  // Wire the API client to this session. A 401 on any authenticated call ends it.
  useEffect(() => {
    configureApiClient({
      getToken: () => tokenRef.current,
      onUnauthorized: () => endSession('expired'),
    });
  }, [endSession]);

  const loadProfile = useCallback(async () => {
    setStatus('checking');
    setProfileError(null);
    try {
      const loaded = await fetchProfile(true);
      setProfile(loaded);
      setStatus('authenticated');
    } catch (error) {
      if (error instanceof ApiError && error.kind === 'unauthorized') return; // endSession ran.
      setProfileError(error instanceof ApiError ? error : new ApiError({ status: 0, kind: 'unexpected' }));
      setStatus('profileError');
    }
  }, []);

  // Restore a session saved in this tab (page refresh).
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    if (tokenRef.current) void loadProfile();
  }, [loadProfile]);

  // Sign out exactly when the token expires.
  useEffect(() => {
    if (!session) return;
    const remaining = session.expiresAt - Date.now();
    const timer = window.setTimeout(() => endSession('expired'), Math.max(0, remaining));
    // Background tabs throttle timers; re-check when the tab becomes visible.
    const onVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() >= session.expiresAt) {
        endSession('expired');
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [session, endSession]);

  // Keep permissions current (e.g. an administrator changed this user's role).
  useEffect(() => {
    if (status !== 'authenticated') return;
    const onFocus = () => {
      fetchProfile(true)
        .then(setProfile)
        .catch(() => {
          // A 401 already ended the session; other failures keep the last profile.
        });
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [status]);

  const login = useCallback(
    async (username: string, password: string) => {
      const token = await apiRequest('/auth/login', {
        method: 'POST',
        form: { username, password },
        schema: tokenResponseSchema,
        handleUnauthorized: false,
      });
      const nextSession: StoredSession = {
        token: token.access_token,
        expiresAt: Date.now() + token.expires_in * 1000,
      };
      tokenRef.current = nextSession.token;
      try {
        const loaded = await fetchProfile(false);
        writeStoredSession(nextSession);
        queryClient.clear();
        setSession(nextSession);
        setProfile(loaded);
        setProfileError(null);
        setSignOutReason(null);
        setStatus('authenticated');
      } catch (error) {
        tokenRef.current = null;
        throw error;
      }
    },
    [queryClient],
  );

  const logout = useCallback(() => endSession('signedOut'), [endSession]);

  const value = useMemo<AuthContextValue>(() => {
    const permissions: ReadonlySet<string> = new Set(profile?.permissions ?? []);
    return {
      status,
      profile,
      permissions,
      expiresAt: session?.expiresAt ?? null,
      signOutReason,
      profileError,
      login,
      logout,
      retryProfile: () => void loadProfile(),
      can: (permission: Permission) => permissions.has(permission),
    };
  }, [status, profile, session, signOutReason, profileError, login, logout, loadProfile]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
