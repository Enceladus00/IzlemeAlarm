import { createContext, useContext } from 'react';
import type { ApiError } from '@/api/client';
import type { Profile } from '@/api/schemas/auth';
import type { Permission, PermissionSet } from './permissions';

export type AuthStatus = 'checking' | 'anonymous' | 'authenticated' | 'profileError';
export type SignOutReason = 'expired' | 'signedOut';

export interface AuthContextValue {
  status: AuthStatus;
  profile: Profile | null;
  permissions: PermissionSet;
  /** Epoch milliseconds when the token expires, or null when signed out. */
  expiresAt: number | null;
  signOutReason: SignOutReason | null;
  profileError: ApiError | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  retryProfile: () => void;
  can: (permission: Permission) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>.');
  return value;
}
