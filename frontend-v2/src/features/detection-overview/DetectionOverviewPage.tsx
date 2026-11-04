import { BellOff, Play, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import type { DashboardSummary } from '@/api/schemas/dashboard';
import { useAuth } from '@/auth/auth-context';
import { BarList } from '@/components/charts/BarList';
import { ChartTableToggle } from '@/components/charts/ChartTableToggle';
import { TrendChart, type TrendSeries } from '@/components/charts/TrendChart';
import { AlertStatusBadge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { StatCard } from '@/components/ui/StatCard';
import { Tabs } from '@/components/ui/Tabs';
import { cn } from '@/utils/cn';
import { formatDate, formatDateTime, formatNumber } from '@/utils/format';
import { OVERVIEW_PERIODS, useDashboardSummary, useEvaluateRules, useLatestAlerts, type OverviewPeriod } from './api';
import { FunnelTab, RulePerformanceTab } from './OverviewTabs';

const SEVERITY_ORDER = ['high', 'medium', 'low'] as const;
const SEVERITY_COLOR: Record<string, string> = {
  high: 'var(--status-critical)',
  medium: 'var(--status-serious)',
  low: 'var(--status-neutral)',
};
const TOP_RULES = 8;

function openAlertCount(summary: DashboardSummary): number {
  return (summary.by_status.new ?? 0) + (summary.by_status.in_review ?? 0);
}

function localToday(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

export default function DetectionOverviewPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { can } = useAuth();
  const [tab, setTab] = useState<'summary' | 'funnel' | 'rules'>('summary');
  const [days, setDays] = useState<OverviewPeriod>(30);
  // Only the open tab (re)loads when the period changes.
  const summary = useDashboardSummary(days, tab === 'summary');
  const latest = useLatestAlerts(can('alert:view'));
  const evaluate = useEvaluateRules();

  const refresh = () => {
    void summary.refetch();
    if (can('alert:view')) void latest.refetch();
  };

  const data = summary.data;
  const fmt = (value: number) => formatNumber(value, language);

  // K3: only the open tab renders, so only its request is sent.
  const summaryContent = (
    <>
      {summary.isError && data && (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} className="mb-4" />
      )}
      {summary.isError && !data ? (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
      ) : (
        <div className={cn('space-y-4 transition-opacity', summary.isFetching && data && 'opacity-70')}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard loading={!data} label={t('detection.transactionsAnalyzed')} value={data && fmt(data.transactions)} />
            <StatCard
              loading={!data}
              label={t('detection.suspiciousTransactions')}
              value={data && fmt(data.suspicious_transactions)}
              caption={t('detection.suspiciousHint')}
              tone={data && data.suspicious_transactions > 0 ? 'danger' : 'default'}
            />
            <StatCard
              loading={!data}
              label={t('detection.alerts')}
              value={data && fmt(data.alerts)}
              caption={data && t('detection.openAlerts', { count: openAlertCount(data) })}
            />
            <StatCard
              loading={!data}
              label={t('detection.customersMonitored')}
              value={data && fmt(data.customers)}
              caption={data && t('detection.accountsCount', { count: data.accounts })}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title={t('detection.trendTitle', { days })} description={t('detection.trendDescription')} />
              <div className="px-5 pb-5">{data ? <TrendPanel summary={data} /> : <ChartSkeleton />}</div>
            </Card>
            <Card>
              <CardHeader title={t('detection.severityTitle')} />
              <div className="px-5 pb-5">
                {data ? (
                  <SeverityPanel summary={data} />
                ) : (
                  <ChartSkeleton short />
                )}
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
            <Card className="xl:col-span-2">
              <CardHeader title={t('detection.rulesTitle')} description={t('detection.rulesDescription')} />
              <div className="px-5 pb-5">{data ? <RulesPanel summary={data} /> : <ChartSkeleton short />}</div>
            </Card>
            <Card className="xl:col-span-3">
              <CardHeader
                title={t('detection.latestTitle')}
                actions={
                  can('alert:view') && (
                    <Link to="/alerts" className="text-[13px] font-semibold text-info underline-offset-2 hover:underline">
                      {t('detection.viewAllAlerts')}
                    </Link>
                  )
                }
              />
              <div className="px-5 pt-3 pb-5">
                {!can('alert:view') ? (
                  <InlineAlert tone="info">{t('detection.latestNoPermission')}</InlineAlert>
                ) : latest.isError ? (
                  <ErrorState error={latest.error} onRetry={() => void latest.refetch()} />
                ) : !latest.data ? (
                  <ChartSkeleton short />
                ) : latest.data.items.length === 0 ? (
                  <EmptyState icon={BellOff} title={t('detection.latestEmpty')} className="py-8" />
                ) : (
                  <div className="-mx-5 overflow-x-auto">
                    <table className="w-full min-w-[560px] text-[13px]">
                      <thead>
                        <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                          <th scope="col" className="px-5 py-2 font-medium">{t('detection.columns.alert')}</th>
                          <th scope="col" className="px-2 py-2 font-medium">{t('detection.columns.rule')}</th>
                          <th scope="col" className="px-2 py-2 font-medium">{t('detection.columns.customer')}</th>
                          <th scope="col" className="px-2 py-2 font-medium">{t('detection.columns.severity')}</th>
                          <th scope="col" className="px-2 py-2 font-medium">{t('detection.columns.status')}</th>
                          <th scope="col" className="px-5 py-2 font-medium">{t('detection.columns.created')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {latest.data.items.map((alert) => (
                          <tr key={alert.alert_id} className="border-b border-border last:border-0">
                            <td className="px-5 py-2.5 font-mono text-muted">
                              <Link to={`/alerts?alert=${alert.alert_id}`} className="hover:text-fg hover:underline">
                                #{alert.alert_id}
                              </Link>
                            </td>
                            <td className="px-2 py-2.5">
                              <span className="rounded bg-neutral-soft px-1.5 py-0.5 font-mono text-xs" title={alert.rule_name}>
                                {alert.rule_code}
                              </span>
                            </td>
                            <td className="px-2 py-2.5 font-medium">{alert.customer_name}</td>
                            <td className="px-2 py-2.5"><SeverityBadge severity={alert.severity} /></td>
                            <td className="px-2 py-2.5"><AlertStatusBadge status={alert.status} /></td>
                            <td className="px-5 py-2.5 whitespace-nowrap text-muted">{formatDateTime(alert.created_at, language)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </Card>
          </div>

          <p className="text-xs text-muted">{t('detection.reportingDate', { date: formatDate(localToday(), language) })}</p>
        </div>
      )}
    </>
  );

  return (
    <>
      <PageHeader
        breadcrumb={t('detection.breadcrumb')}
        title={t('nav.detectionOverview')}
        description={t('detection.description')}
        actions={
          <>
            <Button onClick={refresh} disabled={summary.isFetching}>
              <RefreshCw className={cn('size-4', summary.isFetching && 'animate-spin')} aria-hidden />
              {t('common.refresh')}
            </Button>
            {can('rule:edit') && (
              <Button variant="primary" loading={evaluate.isPending} onClick={() => evaluate.mutate()}>
                {!evaluate.isPending && <Play className="size-4" aria-hidden />}
                {evaluate.isPending ? t('detection.evaluating') : t('detection.evaluate')}
              </Button>
            )}
          </>
        }
      />

      {evaluate.isSuccess && (
        <InlineAlert tone="success" className="mb-4" live>
          {t('detection.evaluateDone', { count: evaluate.data.created_alerts })}
        </InlineAlert>
      )}
      {evaluate.isError && <ErrorState error={evaluate.error} className="mb-4" />}

      <div className="mb-4 flex items-center justify-end gap-2">
        <label htmlFor="overview-period" className="text-[13px] text-muted">
          {t('overviewTabs.period')}
        </label>
        <Select
          id="overview-period"
          className="w-36"
          value={String(days)}
          onChange={(event) => setDays(Number(event.target.value) as OverviewPeriod)}
        >
          {OVERVIEW_PERIODS.map((period) => (
            <option key={period} value={period}>
              {t('overviewTabs.days', { count: period })}
            </option>
          ))}
        </Select>
      </div>
      <Tabs
        label={t('overviewTabs.label')}
        value={tab}
        onChange={setTab}
        items={[
          { value: 'summary', label: t('overviewTabs.summary'), content: summaryContent },
          { value: 'funnel', label: t('overviewTabs.funnel'), content: <FunnelTab days={days} /> },
          { value: 'rules', label: t('overviewTabs.rules'), content: <RulePerformanceTab days={days} /> },
        ]}
      />
    </>
  );
}

function ChartSkeleton({ short = false }: { short?: boolean }) {
  return <div className={cn('animate-pulse rounded-md bg-neutral-soft', short ? 'h-40' : 'h-60')} aria-hidden />;
}

function TrendPanel({ summary }: { summary: DashboardSummary }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const series: TrendSeries[] = [
    { key: 'alerts', label: t('detection.trendAlerts'), color: 'var(--series-1)' },
    { key: 'suspicious_transactions', label: t('detection.trendSuspicious'), color: 'var(--series-2)' },
  ];
  const points = summary.trends.map((row) => ({
    date: row.date,
    values: { alerts: row.alerts, suspicious_transactions: row.suspicious_transactions },
  }));
  const hasData = summary.trends.some((row) => row.alerts > 0 || row.suspicious_transactions > 0);

  return (
    <>
      {!hasData && <p className="mb-2 text-[13px] text-muted">{t('detection.trendEmpty')}</p>}
      <ChartTableToggle
        chart={(toggle) => (
          <TrendChart series={series} points={points} title={t('detection.trendTitle', { days: summary.days })} toolbar={toggle} />
        )}
        table={
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-[13px]">
              <thead className="sticky top-0 bg-surface">
                <tr className="border-b border-border text-left text-xs text-muted">
                  <th scope="col" className="py-1.5 font-medium">{t('charts.date')}</th>
                  {series.map((s) => (
                    <th key={s.key} scope="col" className="py-1.5 text-right font-medium">{s.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.trends.map((row) => (
                  <tr key={row.date} className="border-b border-border last:border-0">
                    <td className="py-1.5">{formatDate(row.date, language)}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(row.alerts, language)}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(row.suspicious_transactions, language)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        }
      />
    </>
  );
}

function SeverityPanel({ summary }: { summary: DashboardSummary }) {
  const { t } = useTranslation();
  const total = Object.values(summary.by_severity).reduce((sum, count) => sum + count, 0);
  if (total === 0) return <EmptyState icon={BellOff} title={t('detection.severityEmpty')} className="py-8" />;

  const extra = Object.keys(summary.by_severity).filter((key) => !(SEVERITY_ORDER as readonly string[]).includes(key));
  const keys = [...SEVERITY_ORDER, ...extra];
  return (
    <>
      <BarList
        label={t('detection.severityTitle')}
        items={keys.map((key) => ({
          key,
          label: <SeverityBadge severity={key} />,
          value: summary.by_severity[key] ?? 0,
          color: SEVERITY_COLOR[key] ?? 'var(--status-neutral)',
        }))}
      />
      <p className="mt-3 text-xs text-muted">{t('detection.openAlertsCaption', { count: openAlertCount(summary) })}</p>
    </>
  );
}

function RulesPanel({ summary }: { summary: DashboardSummary }) {
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const entries = Object.entries(summary.by_rule).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const triggered = entries.filter(([, count]) => count > 0);
  if (triggered.length === 0) return <EmptyState title={t('detection.rulesEmpty')} className="py-8" />;

  const visible = showAll ? triggered : triggered.slice(0, TOP_RULES);
  const zero = entries.length - triggered.length;
  return (
    <>
      <BarList
        label={t('detection.rulesTitle')}
        items={visible.map(([code, count]) => ({ key: code, label: <span className="font-mono">{code}</span>, value: count }))}
      />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>{zero > 0 && t('detection.rulesZeroNote', { count: zero })}</span>
        {triggered.length > TOP_RULES && (
          <Button size="sm" variant="ghost" onClick={() => setShowAll((value) => !value)} aria-expanded={showAll}>
            {showAll ? t('detection.rulesShowTop', { count: TOP_RULES }) : t('detection.rulesShowAll', { count: triggered.length })}
          </Button>
        )}
      </div>
    </>
  );
}
