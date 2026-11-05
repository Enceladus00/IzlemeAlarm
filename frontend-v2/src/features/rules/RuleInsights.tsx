import { ChevronDown, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RulePerformance } from '@/api/schemas/dashboard';
import { CUSTOMER_TYPES, PARAMETER_STATUSES, type CustomerType, type ParameterStatus } from '@/api/schemas/rules';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { needsReview, REVIEW_HIT_RATE, REVIEW_PERIOD_DAYS } from '@/features/detection-overview/review';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';
import { useRuleHistory } from './api';

/** E07: how the rule has performed lately, with the "gözden geçir" flag. */
export function RulePerformanceSummary({ row }: { row: RulePerformance[number] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const fmt = (value: number) => formatNumber(value, language);
  const review = needsReview(row);
  return (
    <div className={cn('rounded-md border px-4 py-3 text-[13px]', review ? 'border-danger bg-danger-soft' : 'border-border')}>
      <p className="mb-1 text-xs font-medium text-muted">{t('ruleReview.title', { days: REVIEW_PERIOD_DAYS })}</p>
      <p>
        {t('ruleReview.summary', { alerts: fmt(row.alerts), confirmed: fmt(row.confirmed), closed: fmt(row.closed) })}
        {' · '}
        <span className="font-semibold">
          {t('ruleReview.hitRate')}:{' '}
          {row.hit_rate === null ? '—' : `%${formatNumber(row.hit_rate * 100, language, { maximumFractionDigits: 1 })}`}
        </span>
      </p>
      {review && (
        <p className="mt-1 flex items-center gap-1.5 font-semibold text-danger">
          <TriangleAlert className="size-4 shrink-0" aria-hidden />
          {t('ruleReview.advice', { threshold: formatNumber(REVIEW_HIT_RATE * 100, language) })}
        </p>
      )}
    </div>
  );
}

/** E07 "Değişiklik geçmişi": who changed what, old → new, and why. Loaded when opened. */
export function RuleHistoryCard({ code }: { code: string }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [open, setOpen] = useState(false);
  const history = useRuleHistory(code, open);

  const fieldLabel = (field: string): string => {
    if (field === 'is_active') return t('rules.ruleActive');
    if (field === 'weight') return t('rules.weight');
    const [type, name] = field.split('.', 2) as [string, string | undefined];
    const typeLabel = (CUSTOMER_TYPES as readonly string[]).includes(type) ? t(`rules.customerTypes.${type as CustomerType}`) : type;
    return name === 'status' ? `${typeLabel} · ${t('ruleHistory.status')}` : `${typeLabel} · ${name ?? ''}`;
  };
  const value = (field: string, raw: unknown): string => {
    if (raw === null || raw === undefined) return '—';
    if (typeof raw === 'boolean') return field === 'is_active' ? (raw ? t('rules.active') : t('rules.inactive')) : String(raw);
    if (field.endsWith('.status') && (PARAMETER_STATUSES as readonly string[]).includes(String(raw))) {
      return t(`rules.statusShort.${raw as ParameterStatus}`);
    }
    return typeof raw === 'object' ? JSON.stringify(raw) : String(raw);
  };

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-5 py-4 text-left text-[15px] font-semibold"
      >
        {t('ruleHistory.title')}
        <ChevronDown className={cn('size-4 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div className="border-t border-border px-5 py-4">
          {history.isError ? (
            <ErrorState error={history.error} onRetry={() => void history.refetch()} />
          ) : !history.data ? (
            <div className="h-16 animate-pulse rounded bg-neutral-soft" aria-hidden />
          ) : history.data.length === 0 ? (
            <EmptyState title={t('ruleHistory.empty')} className="py-4" />
          ) : (
            <ol className="space-y-4">
              {history.data.map((entry) => (
                <li key={entry.change_id} className="space-y-1.5 border-l-2 border-border pl-4 text-[13px]">
                  <p className="text-xs text-muted">
                    <span className="font-semibold text-fg">{entry.actor_name ?? '—'}</span>
                    {entry.actor_role && <> · {t(`roles.${entry.actor_role as 'analyst'}`, { defaultValue: entry.actor_role })}</>}
                    {' · '}
                    {formatDateTime(entry.changed_at, language)}
                  </p>
                  {entry.reason && <blockquote className="bg-neutral-soft px-3 py-1.5 whitespace-pre-line">{entry.reason}</blockquote>}
                  {entry.changes.length === 0 ? (
                    <p className="text-muted">{t('ruleHistory.noChanges')}</p>
                  ) : (
                    <ul className="space-y-0.5">
                      {entry.changes.map((change) => (
                        <li key={change.field}>
                          <span className="text-muted">{fieldLabel(change.field)}:</span>{' '}
                          <span className="font-mono line-through decoration-muted">{value(change.field, change.old)}</span>
                          {' → '}
                          <span className="font-mono font-semibold">{value(change.field, change.new)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Card>
  );
}
