import { BellOff, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';
import { AlertStatusBadge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';
import { ALL_ALERTS_PAGE_SIZE, useAlertList, useRuleCodes } from './api';

const STATUS_TABS = ['all', 'new', 'in_review', 'closed', 'confirmed_suspicious'] as const;
type StatusTab = (typeof STATUS_TABS)[number];
const SEVERITIES = ['high', 'medium', 'low'] as const;

function oneOf<T extends string>(value: string | null, options: readonly T[], fallback: T): T {
  return value !== null && (options as readonly string[]).includes(value) ? (value as T) : fallback;
}

/**
 * E11 "Tüm alarmlar": every alert in any status for compliance, with per-status
 * counts under the same filters. Opening a closed alert shows its decision summary.
 */
export default function AllAlertsPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [params, setParams] = useSearchParams();
  const status = oneOf(params.get('status'), STATUS_TABS, 'all');
  const severity = oneOf(params.get('severity'), ['', ...SEVERITIES] as const, '');
  const rule = params.get('rule') ?? '';
  const dateFrom = params.get('from') ?? '';
  const pageIndex = Math.max(0, (Number(params.get('page') ?? '1') || 1) - 1);
  const ruleCodes = useRuleCodes();

  const update = (patch: Record<string, string>) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(patch)) {
          if (value === '' || (key === 'status' && value === 'all') || (key === 'page' && value === '1')) next.delete(key);
          else next.set(key, value);
        }
        if (!('page' in patch)) next.delete('page');
        return next;
      },
      { replace: true },
    );

  const list = useAlertList({
    status: status === 'all' ? undefined : status,
    severity: severity || undefined,
    rule_code: rule || undefined,
    date_from: dateFrom || undefined,
    offset: pageIndex * ALL_ALERTS_PAGE_SIZE,
    limit: ALL_ALERTS_PAGE_SIZE,
  });
  const counts = list.data?.counts_by_status;
  const countFor = (tab: StatusTab): number | undefined =>
    counts === undefined
      ? undefined
      : tab === 'all'
        ? counts.new + counts.in_review + counts.closed + counts.confirmed_suspicious
        : counts[tab];
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / ALL_ALERTS_PAGE_SIZE)) : 1;
  const tabLabel = (tab: StatusTab) => (tab === 'all' ? t('allAlerts.all') : t(`alertStatus.${tab}`));

  return (
    <>
      <PageHeader breadcrumb={t('allAlerts.breadcrumb')} title={t('nav.allAlerts')} description={t('allAlerts.description')} />

      <div role="group" aria-label={t('allAlerts.statusLabel')} className="mb-4 flex flex-wrap gap-1.5">
        {STATUS_TABS.map((tab) => {
          const count = countFor(tab);
          return (
            <button
              key={tab}
              type="button"
              aria-pressed={status === tab}
              onClick={() => update({ status: tab })}
              className={cn(
                'rounded-full border px-3 py-1.5 text-[13px] font-medium',
                status === tab ? 'border-accent bg-accent-soft' : 'border-border hover:bg-surface-hover',
              )}
            >
              {tabLabel(tab)}
              {count !== undefined && <span className="ml-1.5 tabular-nums text-muted">{formatNumber(count, language)}</span>}
            </button>
          );
        })}
      </div>

      <Card className="mb-4 grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
        <Field label={t('allAlerts.severity')}>
          <Select value={severity} onChange={(event) => update({ severity: event.target.value })}>
            <option value="">{t('allAlerts.any')}</option>
            {SEVERITIES.map((value) => (
              <option key={value} value={value}>
                {t(`severity.${value}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('allAlerts.rule')}>
          <Select value={rule} onChange={(event) => update({ rule: event.target.value })}>
            <option value="">{t('allAlerts.any')}</option>
            {(ruleCodes.data ?? []).map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('allAlerts.dateFrom')}>
          <Input type="date" value={dateFrom} onChange={(event) => update({ from: event.target.value })} />
        </Field>
      </Card>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : !list.data ? (
        <div className="h-48 animate-pulse rounded-md bg-neutral-soft" aria-hidden />
      ) : list.data.items.length === 0 ? (
        <Card>
          <EmptyState icon={BellOff} title={t('allAlerts.empty')} />
        </Card>
      ) : (
        <Card className={cn('overflow-hidden', list.isPlaceholderData && 'opacity-70')}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-[13px]" aria-label={t('nav.allAlerts')}>
              <thead>
                <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                  <th scope="col" className="px-5 py-2 font-medium">{t('allAlerts.columns.alert')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('allAlerts.columns.customer')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('allAlerts.columns.rule')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('allAlerts.severity')}</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">{t('allAlerts.columns.score')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('allAlerts.columns.status')}</th>
                  <th scope="col" className="px-5 py-2 font-medium">{t('allAlerts.columns.created')}</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((alert) => (
                  <tr key={alert.alert_id} className="border-b border-border last:border-0">
                    <td className="px-5 py-2.5">
                      <Link
                        to={`/alerts/${alert.alert_id}`}
                        state={{ backSearch: '' }}
                        className="font-mono font-semibold text-info hover:underline"
                      >
                        #{alert.alert_id}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="font-medium">{alert.customer_name}</span>
                      <span className="block font-mono text-xs text-muted">{alert.customer_no}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="font-mono font-semibold">{alert.rule_code}</span>{' '}
                      <span className="text-muted">{alert.rule_name}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <SeverityBadge severity={alert.severity} />
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono">
                      {alert.score === null ? '—' : formatNumber(alert.score, language, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                    </td>
                    <td className="px-3 py-2.5">
                      <AlertStatusBadge status={alert.status} />
                    </td>
                    <td className="px-5 py-2.5 whitespace-nowrap text-muted">{formatDateTime(alert.created_at, language)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="flex items-center justify-between gap-2 border-t border-border px-5 py-3 text-xs text-muted" aria-label={t('allAlerts.pagination')}>
            <span>{t('allAlerts.total', { count: list.data.total })}</span>
            {pages > 1 && (
              <span className="flex items-center gap-2">
                <Button size="sm" disabled={pageIndex === 0} onClick={() => update({ page: String(pageIndex) })}>
                  <ChevronLeft className="size-4" aria-hidden />
                  {t('common.previous')}
                </Button>
                <span>{t('allAlerts.pageOf', { page: pageIndex + 1, pages })}</span>
                <Button size="sm" disabled={pageIndex + 1 >= pages} onClick={() => update({ page: String(pageIndex + 2) })}>
                  {t('common.next')}
                  <ChevronRight className="size-4" aria-hidden />
                </Button>
              </span>
            )}
          </nav>
        </Card>
      )}
    </>
  );
}
