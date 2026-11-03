import { BellOff, ChevronRight, Search, SearchX } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router';
import { ALERT_SEVERITIES, ALERT_STATUSES, type AlertSummary } from '@/api/schemas/alerts';
import { AlertStatusBadge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { FilterChip } from '@/components/ui/FilterChip';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/PageHeader';
import { Placeholder } from '@/components/ui/Placeholder';
import { StatCard } from '@/components/ui/StatCard';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';
import { QUEUE_PAGE_SIZE, useAlertCount, useAlertQueue, useRuleCodes } from './api';
import {
  DATE_RANGES,
  DEFAULT_FILTERS,
  hasInvalidRange,
  parseFilters,
  toApiQuery,
  toSearchParams,
  type QueueFilters,
} from './filters';
import { groupAlertsByCustomer, matchesSearch, type CustomerGroup } from './grouping';

const ROW_GRID =
  'md:grid md:grid-cols-[minmax(180px,2fr)_minmax(120px,1.4fr)_110px_64px_80px_minmax(130px,1.4fr)_96px] md:items-center md:gap-3';

function distinctCustomers(alerts: AlertSummary[]): number {
  return new Set(alerts.map((alert) => alert.customer_no)).size;
}

export default function AlertQueuePage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const [today] = useState(() => new Date());
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const filters = parseFilters(params);
  const invalidRange = hasInvalidRange(filters);
  const apiQuery = useMemo(() => toApiQuery(filters, today), [filters.status, filters.severity, filters.rule, filters.range, filters.from, filters.to, today]); // eslint-disable-line react-hooks/exhaustive-deps

  const queue = useAlertQueue(apiQuery, !invalidRange);
  const pending = useAlertQueue({ status: 'new' });
  const highPending = useAlertCount({ status: 'new', severity: 'high' });
  const ruleCodes = useRuleCodes();

  const legacyLink = params.get('alert');
  if (legacyLink && /^\d+$/.test(legacyLink)) return <Navigate to={`/alerts/${legacyLink}`} replace />;

  const setFilters = (patch: Partial<QueueFilters>) =>
    setParams(toSearchParams({ ...filters, ...patch }), { replace: true });

  const loadedAlerts = queue.data?.pages.flatMap((page) => page.items) ?? [];
  const total = queue.data?.pages[0]?.total ?? 0;
  const groups = groupAlertsByCustomer(loadedAlerts, today);
  const visibleGroups = groups.filter((group) => matchesSearch(group, filters.q));
  const partial = loadedAlerts.length < total;

  // KPI: pending alerts and the customers behind them.
  const pendingAlerts = pending.data?.pages[0]?.items ?? [];
  const pendingTotal = pending.data?.pages[0]?.total;
  const pendingComplete = pendingTotal !== undefined && pendingAlerts.length >= pendingTotal;
  const highAlerts = pendingAlerts.filter((alert) => alert.severity === 'high');
  const customersCaption = (count: number) =>
    pendingComplete ? t('alerts.kpiCustomers', { count }) : t('alerts.kpiCustomersAtLeast', { count });

  const toggle = (customerNo: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(customerNo)) next.delete(customerNo);
      else next.add(customerNo);
      return next;
    });

  const isDefault = toSearchParams(filters).toString() === toSearchParams(DEFAULT_FILTERS).toString();

  return (
    <>
      <PageHeader
        breadcrumb={t('alerts.breadcrumb')}
        title={t('alerts.title')}
        actions={
          <div className="relative w-full sm:w-72">
            <label htmlFor="alert-search" className="sr-only">
              {t('alerts.searchLabel')}
            </label>
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" aria-hidden />
            <Input
              id="alert-search"
              type="search"
              value={filters.q}
              onChange={(event) => setFilters({ q: event.target.value })}
              placeholder={t('alerts.searchLabel')}
              title={t('alerts.searchHint')}
              className="pl-9"
            />
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          loading={pending.isPending}
          label={t('alerts.kpiPending')}
          value={pendingTotal !== undefined && formatNumber(pendingTotal, language)}
          caption={customersCaption(distinctCustomers(pendingAlerts))}
        />
        <StatCard
          loading={highPending.isPending || pending.isPending}
          label={t('alerts.kpiHigh')}
          value={highPending.data !== undefined && formatNumber(highPending.data, language)}
          caption={customersCaption(distinctCustomers(highAlerts))}
          tone={highPending.data ? 'danger' : 'default'}
        />
        <StatCard label={t('alerts.kpiDecidedToday')} value={<Placeholder>—</Placeholder>} caption={t('alerts.kpiNotTracked')} />
        <StatCard label={t('alerts.kpiReturned')} value={<Placeholder>—</Placeholder>} caption={t('alerts.kpiNotTracked')} />
      </div>

      <div className="mt-6 mb-3 flex flex-wrap items-center gap-2">
        <FilterChip
          label={t('alerts.filterStatus')}
          value={filters.status}
          active
          onChange={(status) => setFilters({ status })}
          options={[
            { value: 'all', label: t('alerts.all') },
            ...ALERT_STATUSES.map((status) => ({ value: status, label: t(`alertStatus.${status}`) })),
          ]}
        />
        <FilterChip
          label={t('alerts.filterSeverity')}
          value={filters.severity}
          onChange={(severity) => setFilters({ severity })}
          options={[
            { value: 'all', label: t('alerts.all') },
            ...ALERT_SEVERITIES.map((severity) => ({ value: severity, label: t(`severity.${severity}`) })),
          ]}
        />
        <FilterChip
          label={t('alerts.filterRule')}
          value={filters.rule}
          onChange={(rule) => setFilters({ rule })}
          options={[
            { value: 'all', label: t('alerts.all') },
            ...(ruleCodes.data ?? (filters.rule !== 'all' ? [filters.rule] : [])).map((code) => ({ value: code, label: code })),
          ]}
        />
        <FilterChip
          label={t('alerts.filterDate')}
          value={filters.range}
          onChange={(range) => setFilters({ range })}
          options={DATE_RANGES.map((range) => ({ value: range, label: t(`alerts.ranges.${range}`) }))}
          footer={(close) =>
            filters.range === 'custom' && (
              <CustomRange filters={filters} onApply={(from, to) => { setFilters({ from, to }); close(); }} />
            )
          }
        />
        {!isDefault && (
          <Button size="sm" variant="ghost" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
            {t('alerts.clearFilters')}
          </Button>
        )}
        <p className="ml-auto text-xs text-muted">{t('alerts.sortNote')}</p>
      </div>

      {invalidRange ? (
        <InlineAlert tone="danger" live>
          {t('alerts.invalidRange')}
        </InlineAlert>
      ) : queue.isError ? (
        <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />
      ) : (
        <Card className={cn('overflow-hidden', queue.isFetching && !queue.isFetchingNextPage && queue.data && 'opacity-70')}>
          <div
            className={cn(ROW_GRID, 'hidden border-b border-border px-5 py-3 text-[11px] font-medium tracking-wide text-muted uppercase')}
            aria-hidden
          >
            <span className="pl-7">{t('alerts.columns.customer')}</span>
            <span>{t('alerts.columns.rules')}</span>
            <span>{t('alerts.columns.severity')}</span>
            <span className="text-right">{t('alerts.columns.count')}</span>
            <span>{t('alerts.columns.oldest')}</span>
            <span className="flex items-center gap-1.5">
              {t('alerts.columns.lastActor')}
              <Placeholder className="py-0 normal-case" />
            </span>
            <span />
          </div>

          {queue.isPending ? (
            <QueueSkeleton />
          ) : loadedAlerts.length === 0 ? (
            <EmptyState
              icon={BellOff}
              title={isDefault ? t('alerts.emptyQueueTitle') : t('alerts.emptyTitle')}
            >
              {isDefault ? t('alerts.emptyQueueBody') : t('alerts.emptyBody')}
            </EmptyState>
          ) : visibleGroups.length === 0 ? (
            <EmptyState icon={SearchX} title={t('alerts.noSearchMatch', { query: filters.q.trim() })} />
          ) : (
            <ul>
              {visibleGroups.map((group) => (
                <GroupRow
                  key={group.customerNo}
                  group={group}
                  expanded={expanded.has(group.customerNo)}
                  onToggle={() => toggle(group.customerNo)}
                  showStatus={filters.status === 'all'}
                  backSearch={location.search}
                />
              ))}
            </ul>
          )}
        </Card>
      )}

      {!invalidRange && queue.data && loadedAlerts.length > 0 && (
        <div className="mt-3 space-y-3">
          {partial && <InlineAlert tone="warning">{t('alerts.partialNote')}</InlineAlert>}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
            <p>
              {partial
                ? t('alerts.footerTotal', { customers: groups.length, loaded: loadedAlerts.length, total })
                : t('alerts.footer', { customers: visibleGroups.length, alerts: visibleGroups.reduce((sum, g) => sum + g.alerts.length, 0) })}
            </p>
            <p>{t('alerts.footerHint')}</p>
          </div>
          {queue.hasNextPage && (
            <div className="flex justify-center">
              <Button loading={queue.isFetchingNextPage} onClick={() => void queue.fetchNextPage()}>
                {t('alerts.loadMore', { count: Math.min(QUEUE_PAGE_SIZE, total - loadedAlerts.length) })}
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function CustomRange({ filters, onApply }: { filters: QueueFilters; onApply: (from: string, to: string) => void }) {
  const { t } = useTranslation();
  const [from, setFrom] = useState(filters.from);
  const [to, setTo] = useState(filters.to);
  const invalid = !!from && !!to && from > to;
  return (
    <div className="mt-1 space-y-2 border-t border-border px-2.5 pt-3 pb-1.5">
      <label className="flex items-center justify-between gap-3">
        <span className="text-muted">{t('alerts.dateFrom')}</span>
        <Input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} className="h-8 w-40" />
      </label>
      <label className="flex items-center justify-between gap-3">
        <span className="text-muted">{t('alerts.dateTo')}</span>
        <Input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} className="h-8 w-40" />
      </label>
      {invalid && <p className="text-xs font-medium text-danger">{t('alerts.invalidRange')}</p>}
      <Button size="sm" variant="primary" className="w-full" disabled={invalid} onClick={() => onApply(from, to)}>
        {t('alerts.apply')}
      </Button>
    </div>
  );
}

function QueueSkeleton() {
  return (
    <div className="space-y-px" aria-hidden>
      {Array.from({ length: 5 }, (_, index) => (
        <div key={index} className="flex items-center gap-4 border-b border-border px-5 py-4 last:border-0">
          <div className="h-4 w-40 animate-pulse rounded bg-neutral-soft" />
          <div className="h-4 w-24 animate-pulse rounded bg-neutral-soft" />
          <div className="ml-auto h-8 w-20 animate-pulse rounded bg-neutral-soft" />
        </div>
      ))}
    </div>
  );
}

function GroupRow({
  group,
  expanded,
  onToggle,
  showStatus,
  backSearch,
}: {
  group: CustomerGroup;
  expanded: boolean;
  onToggle: () => void;
  showStatus: boolean;
  backSearch: string;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const navigate = useNavigate();
  const panelId = `alerts-${group.customerNo}`;
  const first = group.alerts[0]!;
  const fieldLabel = (text: string) => <span className="mr-2 text-xs text-muted md:sr-only">{text}</span>;

  return (
    <li className={cn('border-b border-border last:border-0', expanded && 'bg-accent-soft')}>
      <div className={cn(ROW_GRID, 'flex flex-col gap-2 px-5 py-3.5')}>
        <div className="flex min-w-0 items-start gap-2">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            aria-controls={panelId}
            aria-label={t('alerts.expandRow', { name: group.customerName })}
            className="mt-0.5 rounded p-0.5 text-muted hover:bg-surface-hover hover:text-fg"
          >
            <ChevronRight className={cn('size-4 transition-transform', expanded && 'rotate-90')} aria-hidden />
          </button>
          <div className="min-w-0">
            <p className="truncate font-semibold">{group.customerName}</p>
            <p className="flex flex-wrap items-center gap-1.5 font-mono text-xs text-muted">
              {group.customerNo} ·<Placeholder className="py-0 font-sans text-[11px]">{t('alerts.customerType')}</Placeholder>
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {fieldLabel(t('alerts.columns.rules'))}
          {group.ruleCodes.map((code) => (
            <span
              key={code}
              className="rounded bg-neutral-soft px-1.5 py-0.5 font-mono text-xs"
              title={group.alerts.find((alert) => alert.rule_code === code)?.rule_name}
            >
              {code}
            </span>
          ))}
        </div>
        <div>
          {fieldLabel(t('alerts.columns.severity'))}
          <SeverityBadge severity={group.maxSeverity} />
        </div>
        <div className="font-semibold tabular-nums md:text-right">
          {fieldLabel(t('alerts.columns.count'))}
          {formatNumber(group.alerts.length, language)}
        </div>
        <div className="text-[13px]">
          {fieldLabel(t('alerts.columns.oldest'))}
          {group.ageDays === 0 ? t('alerts.today') : t('alerts.days', { count: group.ageDays })}
        </div>
        <div className="text-muted">
          {fieldLabel(t('alerts.columns.lastActor'))}—
        </div>
        <div className="md:text-right">
          <Button
            size="sm"
            variant={expanded ? 'primary' : 'secondary'}
            aria-label={t('alerts.reviewCustomer', { name: group.customerName })}
            onClick={() => navigate(`/alerts/${first.alert_id}`, { state: { backSearch } })}
          >
            {t('alerts.review')}
          </Button>
        </div>
      </div>

      {expanded && (
        <ul id={panelId} className="border-t border-border/70 px-5 pt-1 pb-3 md:pl-12">
          {group.alerts.map((alert) => (
            <li key={alert.alert_id} className="border-b border-dashed border-accent/40 last:border-0">
              <Link
                to={`/alerts/${alert.alert_id}`}
                state={{ backSearch }}
                className="grid grid-cols-[64px_1fr] gap-x-3 gap-y-0.5 rounded py-2 text-[13px] hover:bg-surface/60 md:grid-cols-[72px_minmax(160px,2fr)_140px_minmax(140px,1.5fr)_auto] md:items-center"
              >
                <span className="font-mono text-muted">#{alert.alert_id}</span>
                <span className="min-w-0 truncate">
                  <span className="font-semibold">{alert.rule_code}</span> · {alert.rule_name}
                </span>
                <span className="col-start-2 text-muted md:col-start-auto">{formatDateTime(alert.created_at, language)}</span>
                <span className="col-start-2 font-mono text-xs md:col-start-auto">
                  {t('alerts.alertLine', { count: alert.transaction_count })}
                  {alert.score !== null &&
                    ` · ${t('alerts.score', { score: formatNumber(alert.score, language, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) })}`}
                </span>
                <span className="col-start-2 flex gap-1.5 md:col-start-auto">
                  {showStatus && <AlertStatusBadge status={alert.status} />}
                  {!showStatus && <SeverityBadge severity={alert.severity} />}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
