import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

/** KPI tile: label · value · optional caption (sentence case, no trailing colon). */
export function StatCard({
  label,
  value,
  caption,
  tone = 'default',
  loading = false,
}: {
  label: ReactNode;
  value: ReactNode;
  caption?: ReactNode;
  tone?: 'default' | 'danger';
  loading?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-4">
      <p className="text-[13px] text-muted">{label}</p>
      {loading ? (
        <div className="mt-2 space-y-2" aria-hidden>
          <div className="h-7 w-20 animate-pulse rounded bg-neutral-soft" />
          <div className="h-3 w-28 animate-pulse rounded bg-neutral-soft" />
        </div>
      ) : (
        <>
          <p className={cn('mt-1 text-[28px] leading-tight font-semibold', tone === 'danger' ? 'text-danger' : 'text-fg')}>
            {value}
          </p>
          {caption && <p className="mt-1 text-xs text-muted">{caption}</p>}
        </>
      )}
    </div>
  );
}
