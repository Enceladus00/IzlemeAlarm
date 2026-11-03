/**
 * The access token is kept in memory and mirrored to sessionStorage, so a page
 * refresh keeps the session but closing the tab ends it. Tokens last 30 minutes
 * (backend/security.py) and cannot be refreshed.
 */
export interface StoredSession {
  token: string;
  /** Epoch milliseconds. */
  expiresAt: number;
}

export const SESSION_STORAGE_KEY = 'sentinel.session';

export function readStoredSession(now: number = Date.now()): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      !parsed ||
      typeof parsed !== 'object' ||
      typeof (parsed as StoredSession).token !== 'string' ||
      typeof (parsed as StoredSession).expiresAt !== 'number'
    ) {
      clearStoredSession();
      return null;
    }
    const session = parsed as StoredSession;
    if (session.expiresAt <= now) {
      clearStoredSession();
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function writeStoredSession(session: StoredSession): void {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage unavailable: the session still works until the page is reloaded.
  }
}

export function clearStoredSession(): void {
  try {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Nothing to clear.
  }
}

/** Formats remaining milliseconds as mm:ss. */
export function formatRemaining(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}
