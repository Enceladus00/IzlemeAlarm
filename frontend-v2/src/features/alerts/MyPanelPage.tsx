import { ArrowRight, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import type { MySummary } from '@/api/schemas/dashboard';
import { useAuth } from '@/auth/auth-context';
import { AlertStatusBadge, SeverityBadge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { DataTable } from '@/components/ui/DataTable';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatCard } from '@/components/ui/StatCard';
import { formatDate, formatDateTime, formatNumber } from '@/utils/format';
import { useAlertQueue, useMySummary } from './api';

const OUTCOME_ORDER = ['confirmed', 'closed', 'returned', 'pending'] as const;
type Outcome = (typeof OUTCOME_ORDER)[number];
/** Same colors as the overview's "Yükseltilenlerin sonucu" bars. */
const OUTCOME_COLOR: Record<Outcome, string> = {
  confirmed: 'var(--status-critical)',
  closed: 'var(--status-neutral)',
  returned: 'var(--series-2)',
  pending: 'var(--status-serious)',
};
const FIRST_LOOK = 3;

/** E08 — the analyst's own day: queue, returned cases, escalation outcomes, today's decisions. */
export default function MyPanelPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { profile } = useAuth();
  const summary = useMySummary();
  const data = summary.data;
  const fmt = (value: number) => formatNumber(value, language);

  return (
    <>
      <PageHeader
        breadcrumb={`${t('myPanel.breadcrumb')} · ${formatDate(new Date().toISOString(), language)}`}
        title={t('myPanel.greeting', { name: profile?.username ?? '' })}
        actions={
          <Link to="/alerts" className="inline-flex items-center gap-1 text-[13px] font-semibold text-info underline-offset-2 hover:underline">
            {t('myPanel.openQueue')}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        }
      />

      {summary.isError ? (
        // Acceptance: without the endpoint the screen does not break.
        <InlineAlert tone="info">
          {t('myPanel.unavailable')}{' '}
          <Link to="/alerts" className="font-semibold underline">
            {t('myPanel.openQueue')}
          </Link>
        </InlineAlert>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              loading={!data}
              label={t('myPanel.kpiQueue')}
              value={data && fmt(data.queue_pending)}
              caption={data && t('myPanel.kpiQueueHigh', { count: data.queue_high })}
              tone={data?.queue_high ? 'danger' : 'default'}
            />
            <StatCard loading={!data} label={t('myPanel.kpiClosedToday')} value={data && fmt(data.closed_today)} />
            <StatCard
              loading={!data}
              label={t('myPanel.kpiEscalatedToday')}
              value={data && fmt(data.escalated_today)}
              caption={data && t('myPanel.kpiEscalatedConfirmed', { count: data.escalated_today_confirmed })}
            />
            <StatCard
              loading={!data}
              label={t('myPanel.kpiReturned')}
              value={data && fmt(data.returned_to_me)}
              caption={t('myPanel.kpiReturnedHint')}
              tone={data?.returned_to_me ? 'danger' : 'default'}
            />
          </div>

          {data && data.returned_cases.length > 0 && <ReturnedCases cases={data.returned_cases} />}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <FirstLook />
            <Card>
              <CardHeader
                title={t('myPanel.outcomeTitle')}
                description={data && data.escalations_30d > 0 ? t('myPanel.outcomeHint', { count: data.escalations_30d }) : undefined}
              />
              <div className="px-5 pb-5">
                {!data ? (
                  <div className="h-24 animate-pulse rounded-md bg-neutral-soft" aria-hidden />
                ) : data.escalations_30d === 0 ? (
                  <p className="text-[13px] text-muted">{t('myPanel.outcomeEmpty')}</p>
                ) : (
                  <OutcomeBar outcome={data.escalation_outcome_30d} />
                )}
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title={t('myPanel.decisionsTitle')} />
            <div className="px-2 pt-2 pb-3">
              {!data ? (
                <div className="mx-3 h-24 animate-pulse rounded-md bg-neutral-soft" aria-hidden />
              ) : data.decisions_today.length === 0 ? (
                <EmptyState title={t('myPanel.decisionsEmpty')} />
              ) : (
                <DataTable
                  label={t('myPanel.decisionsTitle')}
                  rows={data.decisions_today}
                  rowKey={(row, index) => `${row.alert_id}-${row.changed_at}-${index}`}
                  minWidth={680}
                  columns={[
                    { key: 'time', header: t('myPanel.time'), render: (row) => <span className="tabular-nums text-muted">{formatDateTime(row.changed_at, language)}</span> },
                    {
                      key: 'customer',
                      header: t('myPanel.customer'),
                      render: (row) => (
                        <Link to={`/alerts/${row.alert_id}`} className="font-semibold text-info underline-offset-2 hover:underline">
                          {row.customer_name}
                        </Link>
                      ),
                    },
                    { key: 'rule', header: t('myPanel.rule'), render: (row) => <span className="font-mono">{row.rule_code}</span> },
                    { key: 'severity', header: t('allAlerts.severity'), render: (row) => <SeverityBadge severity={row.severity} /> },
                    { key: 'decision', header: t('myPanel.decision'), render: (row) => <AlertStatusBadge status={row.new_status} /> },
                    { key: 'note', header: t('myPanel.note'), render: (row) => <span className="text-muted">{row.note ?? '—'}</span> },
                  ]}
                />
              )}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

function ReturnedCases({ cases }: { cases: MySummary['returned_cases'] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  return (
    <section aria-label={t('myPanel.returnedTitle')} className="rounded-lg border border-info/40 bg-info-soft p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-info">
        <Undo2 className="size-4" aria-hidden />
        {t('myPanel.returnedTitle')}
      </h2>
      <ul className="space-y-3">
        {cases.map((item) => (
          <li key={item.customer_no} className="flex flex-wrap items-start justify-between gap-3 rounded-md bg-surface p-3">
            <div className="min-w-0">
              <p className="text-[13px] font-semibold">
                {item.customer_name} <span className="font-mono text-xs font-normal text-muted">{item.rule_codes.join(', ')}</span>
              </p>
              <p className="text-xs text-muted">
                {t('myPanel.returnedBy', { name: item.returned_by ?? '—', date: formatDateTime(item.returned_at, language) })}
              </p>
              {item.note && <blockquote className="mt-2 border-l-2 border-info pl-3 text-[13px] italic">{item.note}</blockquote>}
            </div>
            <Link
              to={`/alerts/${item.alert_ids[0]}`}
              className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border-strong px-3 py-1.5 text-[13px] font-semibold hover:bg-surface-hover"
            >
              {t('myPanel.backToReview')}
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function FirstLook() {
  const { t } = useTranslation();
  const queue = useAlertQueue({ status: 'new', sort: 'severity_age', offset: 0, limit: FIRST_LOOK });
  const items = queue.data?.items.slice(0, FIRST_LOOK) ?? [];
  return (
    <Card>
      <CardHeader title={t('myPanel.firstTitle')} description={t('myPanel.firstHint')} />
      <div className="px-5 pb-5">
        {queue.isError ? (
          <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />
        ) : !queue.data ? (
          <div className="h-24 animate-pulse rounded-md bg-neutral-soft" aria-hidden />
        ) : items.length === 0 ? (
          <p className="text-[13px] text-muted">{t('myPanel.firstEmpty')}</p>
        ) : (
          <ol className="divide-y divide-border" aria-label={t('myPanel.firstTitle')}>
            {items.map((item) => (
              <li key={item.customer_no}>
                <Link to={`/alerts/${item.alert_ids[0]}`} className="flex items-center justify-between gap-3 py-2.5 text-[13px] hover:bg-surface-hover">
                  <span className="min-w-0">
                    <span className="block truncate font-semibold">{item.customer_name}</span>
                    <span className="font-mono text-xs text-muted">{item.rule_codes.join(', ')}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-muted">{t('myPanel.alertsCount', { count: item.alert_count })}</span>
                    <SeverityBadge severity={item.severity} />
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}

/** One stacked bar; four segments always add up to escalations_30d. Direct-labeled legend below. */
function OutcomeBar({ outcome }: { outcome: MySummary['escalation_outcome_30d'] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const total = OUTCOME_ORDER.reduce((sum, key) => sum + outcome[key], 0);
  const label = (key: Outcome) => t(`overviewTabs.${key}`);
  return (
    <div>
      <div className="flex h-4 gap-[2px] overflow-hidden rounded" role="img" aria-label={`${t('myPanel.outcomeChart')}: ${OUTCOME_ORDER.map((key) => `${label(key)} ${outcome[key]}`).join(', ')}`}>
        {OUTCOME_ORDER.filter((key) => outcome[key] > 0).map((key) => (
          <div
            key={key}
            title={`${label(key)}: ${formatNumber(outcome[key], language)}`}
            style={{ width: `${(outcome[key] / total) * 100}%`, background: OUTCOME_COLOR[key] }}
          />
        ))}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-[13px] sm:grid-cols-4" data-testid="outcome-legend">
        {OUTCOME_ORDER.map((key) => (
          <div key={key} className="flex items-center gap-2">
            <span className="size-2.5 shrink-0 rounded-sm" style={{ background: OUTCOME_COLOR[key] }} aria-hidden />
            <dt className="text-muted">{label(key)}</dt>
            <dd className="ml-auto font-semibold tabular-nums sm:ml-0">{formatNumber(outcome[key], language)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
