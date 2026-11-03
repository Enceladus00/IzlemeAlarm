import { formatRemaining, readStoredSession, SESSION_STORAGE_KEY } from '@/auth/session';
import { formatDateTime, formatMoney, formatNumber, parseApiDate } from './format';

describe('formatting', () => {
  it('formats money per language without currency conversion', () => {
    expect(formatMoney(45000, 'TRY', 'tr')).toBe('45.000,00 TRY');
    expect(formatMoney('18850.5', 'USD', 'en')).toBe('18,850.50 USD');
    expect(formatMoney(null, 'TRY', 'tr')).toBe('—');
  });

  it('formats integers per language', () => {
    expect(formatNumber(186420, 'tr')).toBe('186.420');
    expect(formatNumber(186420, 'en')).toBe('186,420');
  });

  it('shows naive API timestamps as recorded (no timezone shift)', () => {
    const parsed = parseApiDate('2026-10-26T14:12:05.123');
    expect(parsed?.getHours()).toBe(14);
    expect(parsed?.getMinutes()).toBe(12);
    expect(formatDateTime('2026-10-26T14:12:05', 'tr')).toBe('26.10.2026 14:12');
    expect(formatDateTime(null, 'tr')).toBe('—');
  });
});

describe('session storage', () => {
  it('formats the remaining time as mm:ss', () => {
    expect(formatRemaining(29 * 60_000 + 5_000)).toBe('29:05');
    expect(formatRemaining(-10)).toBe('00:00');
  });

  it('discards an expired stored session', () => {
    sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ token: 't', expiresAt: Date.now() - 1 }));
    expect(readStoredSession()).toBeNull();
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it('discards a malformed stored session', () => {
    sessionStorage.setItem(SESSION_STORAGE_KEY, '{"token":1}');
    expect(readStoredSession()).toBeNull();
  });
});
