import { BellOff, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router';
import {
  ALERT_SEVERITIES,
  QUEUE_STATUSES,
  type AlertQueueItem,
  type QueueStatus,
} from '@/api/schemas/alerts';
import { useAuth } from '@/auth/auth-context';
import { AlertStatusBadge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { FilterChip } from '@/components/ui/FilterChip';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatCard } from '@/components/ui/StatCard';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';
import { QUEUE_PAGE_SIZE, useAlertQueue, useCustomerAlerts, useRuleCodes } from './api';
import {
  ANALYST_DEFAULTS,
  COMPLIANCE_DEFAULTS,
  DATE_RANGES,
  QUEUE_SORTS,
  hasInvalidRange,
  parseFilters,
  toApiQuery,
  toSearchParams,
  type QueueFilters,
} from './filters';
import { ageInDays } from './grouping';
import { MySummaryCards } from './MySummaryCards';
import { isComplianceUser } from './workflow';

const ROW_GRID =
  'md:grid md:grid-cols-[minmax(180px,2fr)_minmax(120px,1.4fr)_110px_64px_80px_minmax(130px,1.4fr)_96px] md:items-center md:gap-3';
const SEARCH_DEBOUNCE_MS = 300;

export default function AlertQueuePage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const { permissions } = useAuth();
  const [today] = useState(() => new Date());
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const defaults = isComplianceUser(permissions) ? COMPLIANCE_DEFAULTS : ANALYST_DEFAULTS;
  const filters = parseFilters(params, defaults);
  const invalidRange = hasInvalidRange(filters);
  const apiQuery = useMemo(
    () => toApiQuery(filters, today, QUEUE_PAGE_SIZE),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [params.toString(), today, defaults.status],
  );
  const queue = useAlertQueue(apiQuery, !invalidRange);
  const ruleCodes = useRuleCodes();

  // The search box updates the URL (and so the server query) after a short pause.
  const [search, setSearch] = useState(filters.q);
  useEffect(() => setSearch(filters.q), [filters.q]);
  useEffect(() => {
    if (search.trim() === filters.q.trim()) return;
    const timer = setTimeout(() => setFilters({ q: search }), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const legacyLink = params.get('alert');
  if (legacyLink && /^\d+$/.test(legacyLink)) return <Navigate to={`/alerts/${legacyLink}`} replace />;

  function setFilters(patch: Partial<QueueFilters>) {
    // Any filter change returns to the first page.
    const next = { ...filters, page: 0, ...patch };
    setParams(toSearchParams(next, defaults), { replace: true });
  }

  const data = queue.data;
  const summary = data?.summary;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / QUEUE_PAGE_SIZE));

  const toggle = (customerNo: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(customerNo)) next.delete(customerNo);
      else next.add(customerNo);
      return next;
    });

  const isDefault = toSearchParams(filters, defaults).toString() === '';
  const flash = (location.state as { flash?: string } | null)?.flash;

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
              value={search}
              maxLength={100}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t('alerts.searchLabel')}
              title={t('alerts.searchHint')}
              className="pl-9"
            />
          </div>
        }
      />

      {flash && (
        <InlineAlert tone="success" live className="mb-4">
          {flash}
        </InlineAlert>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          loading={queue.isPending}
          label={t('alerts.kpiPending')}
          value={summary && formatNumber(summary.alerts, language)}
          caption={summary && t('alerts.kpiCustomers', { count: summary.customers })}
        />
        <StatCard
          loading={queue.isPending}
          label={t('alerts.kpiHigh')}
          value={summary && formatNumber(summary.high_alerts, language)}
          caption={summary && t('alerts.kpiCustomers', { count: summary.high_customers })}
          tone={summary?.high_alerts ? 'danger' : 'default'}
        />
        <MySummaryCards />
      </div>

      <div className="mt-6 mb-3 flex flex-wrap items-center gap-2">
        <FilterChip
          label={t('alerts.filterStatus')}
          value={filters.status}
          active
          onChange={(status) => setFilters({ status: status as QueueStatus })}
          options={QUEUE_STATUSES.map((status) => ({ value: status, label: t(`alerts.queueStatus.${status}`) }))}
        />
        <FilterChip
          label={t('alerts.filterSeverity')}
          value={filters.severity}
          onChange={(severity) => setFilters({ severity: severity as QueueFilters['severity'] })}
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
          onChange={(range) => setFilters({ range: range as QueueFilters['range'] })}
          options={DATE_RANGES.map((range) => ({ value: range, label: t(`alerts.ranges.${range}`) }))}
          footer={(close) =>
            filters.range === 'custom' && (
              <CustomRange filters={filters} onApply={(from, to) => { setFilters({ from, to }); close(); }} />
            )
          }
        />
        <FilterChip
          label={t('alerts.filterSort')}
          value={filters.sort}
          onChange={(sort) => setFilters({ sort: sort as QueueFilters['sort'] })}
          options={QUEUE_SORTS.map((sort) => ({ value: sort, label: t(`alerts.sorts.${sort}`) }))}
        />
        {!isDefault && (
          <Button size="sm" variant="ghost" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
            {t('alerts.clearFilters')}
          </Button>
        )}
      </div>

      {invalidRange ? (
        <InlineAlert tone="danger" live>
          {t('alerts.invalidRange')}
        </InlineAlert>
      ) : queue.isError ? (
        <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />
      ) : (
        <Card className={cn('overflow-hidden', queue.isFetching && data && 'opacity-70')}>
          <div
            className={cn(ROW_GRID, 'hidden border-b border-border px-5 py-3 text-[11px] font-medium tracking-wide text-muted uppercase')}
            aria-hidden
          >
            <span className="pl-7">{t('alerts.columns.customer')}</span>
            <span>{t('alerts.columns.rules')}</span>
            <span>{t('alerts.columns.severity')}</span>
            <span className="text-right">{t('alerts.columns.count')}</span>
            <span>{filters.status === 'in_review' ? t('alerts.columns.waiting') : t('alerts.columns.oldest')}</span>
            <span>{filters.status === 'in_review' ? t('alerts.columns.escalatedBy') : t('alerts.columns.lastActor')}</span>
            <span />
          </div>

          {queue.isPending ? (
            <QueueSkeleton />
          ) : items.length === 0 ? (
            <EmptyState icon={BellOff} title={isDefault ? t('alerts.emptyQueueTitle') : t('alerts.emptyTitle')}>
              {isDefault ? t('alerts.emptyQueueBody') : t('alerts.emptyBody')}
            </EmptyState>
          ) : (
            <ul>
              {items.map((item) => (
                <GroupRow
                  key={item.customer_no}
                  item={item}
                  status={filters.status}
                  today={today}
                  expanded={expanded.has(item.customer_no)}
                  onToggle={() => toggle(item.customer_no)}
                  backSearch={location.search}
                />
              ))}
            </ul>
          )}
        </Card>
      )}

      {!invalidRange && data && items.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
          <p>{t('alerts.footer', { customers: total, alerts: summary?.alerts ?? 0 })}</p>
          {pageCount > 1 && (
            <nav className="flex items-center gap-2" aria-label={t('alerts.pagination')}>
              <Button size="sm" disabled={filters.page === 0} onClick={() => setFilters({ page: filters.page - 1 })}>
                <ChevronLeft className="size-4" aria-hidden />
                {t('common.previous')}
              </Button>
              <span>{t('alerts.pageOf', { page: filters.page + 1, pages: pageCount })}</span>
              <Button
                size="sm"
                disabled={filters.page + 1 >= pageCount}
                onClick={() => setFilters({ page: filters.page + 1 })}
              >
                {t('common.next')}
                <ChevronRight className="size-4" aria-hidden />
              </Button>
            </nav>
          )}
          <p className="w-full">{t('alerts.footerHint')}</p>
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

function customerTypeKey(type: string | null): 'customerType.BIREYSEL' | 'customerType.KURUMSAL' | 'customerType.unknown' {
  if (type === 'BIREYSEL') return 'customerType.BIREYSEL';
  if (type === 'KURUMSAL') return 'customerType.KURUMSAL';
  return 'customerType.unknown';
}

function GroupRow({
  item,
  status,
  today,
  expanded,
  onToggle,
  backSearch,
}: {
  item: AlertQueueItem;
  status: QueueStatus;
  today: Date;
  expanded: boolean;
  onToggle: () => void;
  backSearch: string;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const navigate = useNavigate();
  const panelId = `alerts-${item.customer_no}`;
  const ageDays = ageInDays(item.oldest_created_at, today);
  const fieldLabel = (text: string) => <span className="mr-2 text-xs text-muted md:sr-only">{text}</span>;
  // E04: in the compliance queue the clock that matters is time since escalation.
  const awaitingDecision = status === 'in_review';
  const waitingDays = item.escalated_at ? ageInDays(item.escalated_at, today) : null;
  const note = item.returned_note
    ? { label: t('alerts.complianceNote'), text: item.returned_note }
    : awaitingDecision && item.escalation_note
      ? { label: t('alerts.analystNote'), text: item.escalation_note }
      : null;

  return (
    <li className={cn('border-b border-border last:border-0', expanded && 'bg-accent-soft')}>
      <div className={cn(ROW_GRID, 'flex flex-col gap-2 px-5 py-3.5')}>
        <div className="flex min-w-0 items-start gap-2">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            aria-controls={panelId}
            aria-label={t('alerts.expandRow', { name: item.customer_name })}
            className="mt-0.5 rounded p-0.5 text-muted hover:bg-surface-hover hover:text-fg"
          >
            <ChevronRight className={cn('size-4 transition-transform', expanded && 'rotate-90')} aria-hidden />
          </button>
          <div className="min-w-0">
            <p className="truncate font-semibold">{item.customer_name}</p>
            <p className="font-mono text-xs text-muted">
              {item.customer_no} · <span className="font-sans">{t(customerTypeKey(item.customer_type))}</span>
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {fieldLabel(t('alerts.columns.rules'))}
          {item.rule_codes.map((code) => (
            <span key={code} className="rounded bg-neutral-soft px-1.5 py-0.5 font-mono text-xs">
              {code}
            </span>
          ))}
        </div>
        <div>
          {fieldLabel(t('alerts.columns.severity'))}
          <SeverityBadge severity={item.severity} />
        </div>
        <div className="font-semibold tabular-nums md:text-right">
          {fieldLabel(t('alerts.columns.count'))}
          {formatNumber(item.alert_count, language)}
        </div>
        {awaitingDecision ? (
          <div className="text-[13px]">
            {fieldLabel(t('alerts.columns.waiting'))}
            {waitingDays === null ? (
              <span className="text-muted">—</span>
            ) : waitingDays === 0 ? (
              t('alerts.waitingToday')
            ) : (
              <span className={cn(waitingDays > 2 && 'font-semibold text-warning')}>
                {t('alerts.waitingDays', { count: waitingDays })}
              </span>
            )}
          </div>
        ) : (
          <div className="text-[13px]">
            {fieldLabel(t('alerts.columns.oldest'))}
            {ageDays === 0 ? t('alerts.today') : t('alerts.days', { count: ageDays })}
          </div>
        )}
        <div className="text-[13px]">
          {fieldLabel(awaitingDecision ? t('alerts.columns.escalatedBy') : t('alerts.columns.lastActor'))}
          {item.returned_by ? (
            <span className="font-medium text-warning">{t('alerts.returnedBy', { name: item.returned_by })}</span>
          ) : awaitingDecision && item.escalated_by ? (
            <span className="font-medium">{item.escalated_by}</span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </div>
        <div className="md:text-right">
          <Button
            size="sm"
            variant={expanded ? 'primary' : 'secondary'}
            aria-label={t('alerts.reviewCustomer', { name: item.customer_name })}
            onClick={() => navigate(`/alerts/${item.alert_ids[0]}`, { state: { backSearch } })}
          >
            {t('alerts.review')}
          </Button>
        </div>
      </div>

      {note && (
        <blockquote className="mx-5 mb-3 border-l-2 border-warning bg-warning-soft px-3 py-2 text-[13px] md:ml-12">
          <span className="mr-1.5 font-semibold">{note.label}:</span>
          <span className="whitespace-pre-line">{note.text}</span>
        </blockquote>
      )}

      {expanded && <ExpandedAlerts id={panelId} item={item} status={status} backSearch={backSearch} />}
    </li>
  );
}

/** The customer's alerts in this queue status, loaded when the row is opened. */
function ExpandedAlerts({
  id,
  item,
  status,
  backSearch,
}: {
  id: string;
  item: AlertQueueItem;
  status: QueueStatus;
  backSearch: string;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const alerts = useCustomerAlerts(item.customer_no, status);
  const wanted = new Set(item.alert_ids);
  const rows = (alerts.data?.items ?? []).filter((alert) => wanted.has(alert.alert_id));
  return (
    <div id={id} className="border-t border-border/70 px-5 pt-1 pb-3 md:pl-12">
      {alerts.isError ? (
        <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
      ) : alerts.isPending ? (
        <div className="my-2 h-10 animate-pulse rounded bg-neutral-soft" aria-hidden />
      ) : (
        <ul>
          {rows.map((alert) => (
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
                  <SeverityBadge severity={alert.severity} />
                  <AlertStatusBadge status={alert.status} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
