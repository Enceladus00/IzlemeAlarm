import { Clock } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/auth-context';
import { formatRemaining } from '@/auth/session';
import { cn } from '@/utils/cn';

const WARNING_MS = 2 * 60 * 1000;

/**
 * Visible countdown (not announced every second). A single polite
 * announcement is made when the session enters its final two minutes.
 */
export function SessionCountdown() {
  const { expiresAt } = useAuth();
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  if (expiresAt === null) return null;
  const remaining = expiresAt - now;
  const time = formatRemaining(remaining);
  const warning = remaining <= WARNING_MS;

  return (
    <div>
      <p
        className={cn(
          'flex items-center gap-2 text-xs tabular-nums',
          warning ? 'font-semibold text-accent' : 'text-sidebar-muted',
        )}
        title={t('auth.sessionRemainingLabel')}
      >
        <Clock className="size-3.5" aria-hidden />
        <span>{t('auth.sessionRemaining', { time })}</span>
      </p>
      <div className="sr-only" aria-live="polite">
        {warning ? t('auth.sessionEndingSoon', { time: formatRemaining(WARNING_MS) }) : ''}
      </div>
    </div>
  );
}
