import { ArrowRight, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import type { SystemOverview } from '@/api/schemas/dashboard';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';
import { useApiHealth, useSystemOverview } from './api';

type Health = 'ok' | 'warning' | 'down' | 'unknown' | 'loading';

const RECORD_KEYS = ['customers', 'accounts', 'transactions', 'alerts'] as const;

function HealthCard({
  title,
  status,
  headline,
  caption,
  neutralHeadline = false,
}: {
  title: string;
  status: Health;
  headline: ReactNode;
  caption?: ReactNode;
  /** Keep the headline in body ink (for counts rather than up/down states). */
  neutralHeadline?: boolean;
}) {
  const dot = {
    ok: 'bg-success',
    warning: 'bg-warning',
    down: 'bg-danger',
    unknown: 'bg-status-neutral',
    loading: 'bg-neutral-soft',
  }[status];
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-4">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <span className={cn('size-2.5 rounded-full', dot)} aria-hidden />
        {title}
      </p>
      {status === 'loading' ? (
        <div className="mt-3 space-y-2" aria-hidden>
          <div className="h-6 w-24 animate-pulse rounded bg-neutral-soft" />
          <div className="h-3 w-36 animate-pulse rounded bg-neutral-soft" />
        </div>
      ) : (
        <>
          <p
            className={cn(
              'mt-2 text-xl font-semibold',
              neutralHeadline
                ? 'text-fg'
                : status === 'ok'
                  ? 'text-success'
                  : status === 'warning'
                    ? 'text-warning'
                    : status === 'down'
                      ? 'text-danger'
                      : 'text-fg',
            )}
          >
            {headline}
          </p>
          {caption && <p className="mt-1 font-mono text-xs break-words text-muted">{caption}</p>}
        </>
      )}
    </div>
  );
}

export default function SystemOverviewPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const overview = useSystemOverview();
  const health = useApiHealth();
  const fetching = overview.isFetching || health.isFetching;

  const refresh = () => {
    void overview.refetch();
    void health.refetch();
  };

  const apiStatus: Health = health.isPending ? 'loading' : health.isError ? 'down' : 'ok';
  const data = overview.data;

  return (
    <>
      <PageHeader
        breadcrumb={t('system.breadcrumb')}
        title={t('nav.systemOverview')}
        description={t('system.description')}
        actions={
          <Button onClick={refresh} disabled={fetching}>
            <RefreshCw className={cn('size-4', fetching && 'animate-spin')} aria-hidden />
            {t('common.refresh')}
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <HealthCard
          title={t('system.api')}
          status={apiStatus}
          headline={apiStatus === 'ok' ? t('system.apiUp') : t('system.apiDown')}
          caption={
            health.data
              ? `GET /health · 200 · ${formatNumber(health.data.latencyMs, language)} ms`
              : health.isError
                ? `GET /health · ${health.error && 'status' in health.error ? String(health.error.status || '—') : '—'}`
                : undefined
          }
        />
        <HealthCard
          title={t('system.database')}
          status={data ? 'ok' : overview.isError ? 'down' : 'loading'}
          headline={data ? t('system.databaseConnected') : t('system.apiDown')}
          caption={
            data
              ? `SELECT 1 · ${formatNumber(data.health.database_latency_ms, language, { maximumFractionDigits: 1 })} ms`
              : undefined
          }
        />
        <HealthCard
          title={t('system.schema')}
          status={schemaStatus(data, overview.isError)}
          headline={
            data?.health.schema_revision && data.health.schema_head
              ? data.health.schema_revision === data.health.schema_head
                ? t('system.schemaUpToDate')
                : t('system.schemaOutdated', { head: data.health.schema_head })
              : t('system.schemaUnknown')
          }
          caption={
            data?.health.schema_revision ? (
              <span title={t('system.schemaHeadNote')}>alembic · {data.health.schema_revision}</span>
            ) : undefined
          }
        />
        <HealthCard
          title={t('system.ruleEngine')}
          status={
            data
              ? data.rules.last_run_status === null || data.rules.last_run_status === 'completed'
                ? 'ok'
                : 'unknown'
              : overview.isError
                ? 'unknown'
                : 'loading'
          }
          neutralHeadline
          headline={data && t('system.activeRules', { count: data.rules.active })}
          caption={data && <RuleRunCaption overview={data} />}
        />
      </div>

      {/* A failed refresh keeps the last good data on screen and explains the failure. */}
      {overview.isError && (
        <ErrorState error={overview.error} onRetry={() => void overview.refetch()} className="mt-4" />
      )}
      {overview.isError && !data ? null : (
        <div className={cn('mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5', fetching && data && 'opacity-70 transition-opacity')}>
          <Card className="xl:col-span-3">
            <CardHeader title={t('system.recordsTitle')} />
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[480px] text-[13px]">
                <thead>
                  <tr className="border-b border-border text-[11px] tracking-wide text-muted uppercase">
                    <th scope="col" className="px-5 py-2 text-left font-medium">{t('system.recordsColumns.table')}</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">{t('system.recordsColumns.total')}</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">{t('system.recordsColumns.last7')}</th>
                    <th scope="col" className="px-5 py-2 text-left font-medium">{t('system.recordsColumns.lastAdded')}</th>
                  </tr>
                </thead>
                <tbody>
                  {RECORD_KEYS.map((key) => {
                    const metric = data?.records[key];
                    return (
                      <tr key={key} className="border-b border-border last:border-0">
                        <th scope="row" className="px-5 py-3 text-left font-medium">{t(`system.recordNames.${key}`)}</th>
                        <td className="px-3 py-3 text-right font-mono tabular-nums">
                          {metric ? formatNumber(metric.total, language) : <CellSkeleton />}
                        </td>
                        <td className="px-3 py-3 text-right font-mono tabular-nums">
                          {metric ? `+${formatNumber(metric.added_last_7_days, language)}` : <CellSkeleton />}
                        </td>
                        <td className="px-5 py-3 font-mono text-xs whitespace-nowrap text-muted">
                          {metric ? formatDateTime(metric.last_added_at, language) : <CellSkeleton />}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="space-y-1 border-t border-border px-5 py-3 text-xs text-muted">
              <p>{t('system.recordsNote')}</p>
              <p>{t('system.accountsNote')}</p>
            </div>
          </Card>

          <Card className="xl:col-span-2">
            <CardHeader title={t('system.securityTitle')} />
            <div className="px-5 pt-3 pb-5">{data ? <SecurityList overview={data} /> : <div className="h-48 animate-pulse rounded bg-neutral-soft" />}</div>
          </Card>
        </div>
      )}
    </>
  );
}

function schemaStatus(data: SystemOverview | undefined, isError: boolean): Health {
  if (!data) return isError ? 'unknown' : 'loading';
  const { schema_revision, schema_head } = data.health;
  if (!schema_revision || !schema_head) return 'unknown';
  return schema_revision === schema_head ? 'ok' : 'warning';
}

function CellSkeleton() {
  return <span className="inline-block h-3 w-12 animate-pulse rounded bg-neutral-soft align-middle" aria-hidden />;
}

function RuleRunCaption({ overview }: { overview: SystemOverview }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { last_run_at, last_run_duration_ms, last_run_status } = overview.rules;
  if (!last_run_at) return <>{t('system.noRuns')}</>;
  const parts = [t('system.lastRun', { date: formatDateTime(last_run_at, language) })];
  if (last_run_duration_ms !== null) {
    parts.push(
      t('system.lastRunDuration', {
        seconds: formatNumber(last_run_duration_ms / 1000, language, { maximumFractionDigits: 1 }),
      }),
    );
  }
  return (
    <>
      {parts.join(' · ')}
      {last_run_status && last_run_status !== 'completed' && (
        <span className="mt-1 block font-sans text-warning">{t('system.lastRunStatus', { status: last_run_status })}</span>
      )}
    </>
  );
}

function SecurityList({ overview }: { overview: SystemOverview }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { can } = useAuth();
  const s = overview.security;
  const rows: Array<[string, ReactNode]> = [
    [t('system.sessionDuration'), t('system.minutes', { count: Math.round(s.session_ttl_seconds / 60) })],
    [
      t('system.demoEndpoint'),
      <span key="demo" className="flex items-center gap-1.5">
        <span className={cn('size-2 rounded-full', s.demo_endpoint_enabled ? 'bg-success' : 'border border-muted')} aria-hidden />
        {s.demo_endpoint_enabled ? t('system.enabled') : t('system.disabled')}
      </span>,
    ],
    [t('system.activeUsers'), `${formatNumber(s.active_users, language)} / ${formatNumber(s.total_users, language)}`],
    [
      t('system.csvLimit'),
      t('system.csvLimitValue', {
        mb: formatNumber(s.csv_max_bytes / (1024 * 1024), language, { maximumFractionDigits: 1 }),
        rows: formatNumber(s.csv_max_rows, language),
      }),
    ],
    [t('system.failedLogins'), formatNumber(s.failed_logins_last_24h, language)],
  ];
  const denied = s.access_denied_last_24h;

  return (
    <>
      <dl className="divide-y divide-border border-t border-border text-[13px]">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-4 py-2.5">
            <dt className="text-muted">{label}</dt>
            <dd className="font-mono text-right">{value}</dd>
          </div>
        ))}
      </dl>
      <div
        className={cn(
          'mt-3 flex items-center justify-between gap-3 rounded-md px-3 py-2.5 text-[13px] font-semibold',
          denied > 0 ? 'bg-danger-soft text-danger' : 'bg-neutral-soft text-muted',
        )}
      >
        <span>{t('system.accessDenied')}</span>
        {can('audit:view') ? (
          <Link
            to="/audit"
            className="inline-flex items-center gap-1 underline underline-offset-2"
            aria-label={`${formatNumber(denied, language)} — ${t('system.openAuditLog')}`}
          >
            {formatNumber(denied, language)}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        ) : (
          <span>{formatNumber(denied, language)}</span>
        )}
      </div>
    </>
  );
}
