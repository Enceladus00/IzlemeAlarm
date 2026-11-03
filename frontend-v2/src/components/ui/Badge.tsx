import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/utils/cn';

type Tone = 'danger' | 'warning' | 'success' | 'info' | 'neutral';

const toneClasses: Record<Tone, string> = {
  danger: 'bg-danger-soft text-danger',
  warning: 'bg-warning-soft text-warning',
  success: 'bg-success-soft text-success',
  info: 'bg-info-soft text-info',
  neutral: 'bg-neutral-soft text-muted',
};

export function Badge({
  tone = 'neutral',
  dot = false,
  children,
  className,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap',
        toneClasses[tone],
        className,
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}

const severityTone: Record<string, Tone> = { high: 'danger', medium: 'warning', low: 'neutral' };

/** Severity is always shown as text + colour, never colour alone. */
export function SeverityBadge({ severity }: { severity: string }) {
  const { t } = useTranslation();
  const known = severity === 'high' || severity === 'medium' || severity === 'low';
  return (
    <Badge tone={severityTone[severity] ?? 'neutral'} dot>
      {known ? t(`severity.${severity}`) : severity}
    </Badge>
  );
}

const statusTone: Record<string, Tone> = {
  new: 'info',
  in_review: 'warning',
  closed: 'neutral',
  confirmed_suspicious: 'danger',
};

export function AlertStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const known = status in statusTone;
  return (
    <Badge tone={statusTone[status] ?? 'neutral'}>
      {known ? t(`alertStatus.${status as 'new'}`) : status}
    </Badge>
  );
}
