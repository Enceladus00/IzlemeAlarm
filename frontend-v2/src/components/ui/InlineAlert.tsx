import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

type Tone = 'info' | 'success' | 'warning' | 'danger';

const tones: Record<Tone, { className: string; Icon: typeof Info }> = {
  info: { className: 'bg-info-soft text-info', Icon: Info },
  success: { className: 'bg-success-soft text-success', Icon: CheckCircle2 },
  warning: { className: 'bg-warning-soft text-warning', Icon: AlertTriangle },
  danger: { className: 'bg-danger-soft text-danger', Icon: XCircle },
};

export function InlineAlert({
  tone = 'info',
  title,
  children,
  className,
  live = false,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  /** Announce to screen readers when it appears (errors/success after an action). */
  live?: boolean;
}) {
  const { className: toneClass, Icon } = tones[tone];
  return (
    <div
      role={live ? (tone === 'danger' ? 'alert' : 'status') : undefined}
      className={cn('flex gap-3 rounded-md px-4 py-3 text-[13px]', toneClass, className)}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-fg">{children}</div>}
      </div>
    </div>
  );
}
