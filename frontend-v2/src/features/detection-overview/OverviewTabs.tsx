import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { StatCard } from '@/components/ui/StatCard';
import { formatNumber } from '@/utils/format';
import { useDashboardSummary, useFunnel, useRulePerformance } from './api';
import { DailyAlertBars } from './DailyAlertBars';
import { needsReview } from './review';

function Skeleton() {
  return <div className="h-48 animate-pulse rounded-md bg-neutral-soft" aria-hidden />;
}

function Bar({ label, value, total, tone }: { label: string; value: number; total: number; tone: string }) {
  const { i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const width = total > 0 ? Math.max(2, Math.round((value / total) * 100)) : 0;
  return (
    <div className="grid grid-cols-[minmax(140px,1fr)_3fr_72px] items-center gap-3 text-[13px]">
      <span>{label}</span>
      <span className="h-3 rounded bg-neutral-soft" aria-hidden>
        <span className="block h-3 rounded" style={{ width: `${width}%`, background: tone }} />
      </span>
      <span className="text-right font-semibold tabular-nums">{formatNumber(value, language)}</span>
    </div>
  );
}

/** K3 tab 2: where did the period's alerts go? Counts only, no customer data. */
export function FunnelTab({ days }: { days: number }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const funnel = useFunnel(days);
  // Daily counts come from the summary (usually already cached from the first tab).
  const summary = useDashboardSummary(days);
  if (funnel.isError) return <ErrorState error={funnel.error} onRetry={() => void funnel.refetch()} />;
  if (!funnel.data) return <Skeleton />;
  const data = funnel.data;
  const outcome = data.escalation_outcome;
  if (data.created === 0) return <EmptyState title={t('overviewTabs.funnelEmpty', { days })} />;
  const percent = (value: number | null) =>
    value === null ? t('overviewTabs.noValue') : formatNumber(value, language, { style: 'percent', maximumFractionDigits: 1 });
  const decided = outcome.confirmed + outcome.closed;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={t('overviewTabs.kpiCreated')} value={formatNumber(data.created, language)} />
        <StatCard label={t('overviewTabs.kpiOpen')} value={formatNumber(data.open, language)} caption={t('overviewTabs.kpiOpenHint')} />
        <StatCard
          label={t('overviewTabs.kpiEscalationRate')}
          value={percent(data.escalation_rate)}
          caption={t('overviewTabs.kpiEscalationHint', { count: data.escalated })}
        />
        <StatCard
          label={t('overviewTabs.kpiDecisionDays')}
          value={
            data.avg_decision_days === null
              ? t('overviewTabs.noValue')
              : t('overviewTabs.kpiDecisionValue', { value: formatNumber(data.avg_decision_days, language, { maximumFractionDigits: 1 }) })
          }
          caption={t('overviewTabs.kpiDecisionHint')}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title={t('overviewTabs.dailyTitle', { days })} description={t('overviewTabs.dailyHint')} />
          <div className="px-5 pb-5">
            {summary.isError ? (
              <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
            ) : summary.data ? (
              <DailyAlertBars days={days} rows={summary.data.trends.map((row) => ({ date: row.date, count: row.alerts }))} />
            ) : (
              <Skeleton />
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title={t('overviewTabs.accuracyTitle')} description={t('overviewTabs.accuracyHint')} />
          <div className="px-5 pb-5" data-testid="escalation-accuracy">
            {decided === 0 ? (
              <p className="text-[13px] text-muted">{t('overviewTabs.accuracyEmpty')}</p>
            ) : (
              <>
                <p className="text-3xl font-bold tabular-nums">{percent(data.confirmed_rate)}</p>
                <p className="mt-1 text-[13px] text-muted">{t('overviewTabs.accuracyDetail', { confirmed: outcome.confirmed, decided })}</p>
              </>
            )}
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title={t('overviewTabs.funnelTitle', { days })} description={t('overviewTabs.funnelHint')} />
          <div className="space-y-3 px-5 pb-5">
            <Bar label={t('overviewTabs.created')} value={data.created} total={data.created} tone="var(--series-1)" />
            <Bar label={t('overviewTabs.analystClosed')} value={data.analyst_closed} total={data.created} tone="var(--status-neutral)" />
            <Bar label={t('overviewTabs.analystOpen')} value={data.analyst_open} total={data.created} tone="var(--series-2)" />
            <Bar label={t('overviewTabs.escalated')} value={data.escalated} total={data.created} tone="var(--status-serious)" />
          </div>
        </Card>
        <Card>
          <CardHeader title={t('overviewTabs.outcomeTitle')} description={t('overviewTabs.outcomeHint')} />
          <div className="space-y-3 px-5 pb-5">
            <Bar label={t('overviewTabs.confirmed')} value={outcome.confirmed} total={data.escalated} tone="var(--status-critical)" />
            <Bar label={t('overviewTabs.closed')} value={outcome.closed} total={data.escalated} tone="var(--status-neutral)" />
            <Bar label={t('overviewTabs.returned')} value={outcome.returned} total={data.escalated} tone="var(--series-2)" />
            <Bar label={t('overviewTabs.pending')} value={outcome.pending} total={data.escalated} tone="var(--status-serious)" />
          </div>
        </Card>
      </div>
    </div>
  );
}

/** K3 tab 3: per-rule evaluated customers, alerts, average score and hit rate. */
export function RulePerformanceTab({ days }: { days: number }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const performance = useRulePerformance(days);
  if (performance.isError) return <ErrorState error={performance.error} onRetry={() => void performance.refetch()} />;
  if (!performance.data) return <Skeleton />;
  const rows = performance.data.filter((row) => row.is_active || row.evaluated > 0 || row.alerts > 0);
  if (rows.length === 0) return <EmptyState title={t('overviewTabs.rulesEmpty')} />;
  const fmt = (value: number) => formatNumber(value, language);
  return (
    <Card>
      <CardHeader title={t('overviewTabs.rulesTitle', { days })} description={t('overviewTabs.rulesHint')} />
      <div className="overflow-x-auto px-2 pb-3">
        <table className="w-full min-w-[720px] text-[13px]" aria-label={t('overviewTabs.rulesTitle', { days })}>
          <thead>
            <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
              <th scope="col" className="px-3 py-2 font-medium">{t('overviewTabs.columns.rule')}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t('overviewTabs.columns.evaluated')}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t('overviewTabs.columns.alerts')}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t('overviewTabs.columns.avgScore')}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t('overviewTabs.columns.confirmed')}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t('overviewTabs.columns.closed')}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t('overviewTabs.columns.hitRate')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.rule_code} className="border-b border-border last:border-0">
                <th scope="row" className="px-3 py-2 text-left font-normal">
                  <span className="font-mono font-semibold">{row.rule_code}</span> {row.name}
                  {row.provisional && (
                    <Badge tone="warning" className="ml-2">
                      {t('overviewTabs.provisional')}
                    </Badge>
                  )}
                </th>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(row.evaluated)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(row.alerts)}</td>
                <td className="px-3 py-2 text-right font-mono">
                  {row.avg_alert_score === null ? '—' : formatNumber(row.avg_alert_score, language, { maximumFractionDigits: 4 })}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(row.confirmed)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmt(row.closed)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {row.hit_rate === null ? '—' : `%${formatNumber(row.hit_rate * 100, language, { maximumFractionDigits: 1 })}`}
                  {needsReview(row) && (
                    <Badge tone="danger" className="ml-2">
                      {t('ruleReview.badge')}
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
