import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, History } from 'lucide-react';
import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';
import { apiRequest } from '@/api/client';
import { auditPageSchema, type AuditEvent } from '@/api/schemas/users';
import { useAuth } from '@/auth/auth-context';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { PageSpinner } from '@/components/ui/Spinner';
import { useUsers } from '@/features/users/api';
import { cn } from '@/utils/cn';
import { formatDateTime } from '@/utils/format';
import { DecisionTrace } from './DecisionTrace';

const PAGE_SIZES = [50, 100, 200] as const;
/** Event types with a Turkish label (API design 7.17). Keys use '_' for '.'. */
const KNOWN_ACTIONS = [
  'LOGIN_SUCCESS',
  'LOGIN_FAILED',
  'LOGIN_RATE_LIMITED',
  'ACCESS_DENIED',
  'USER_CREATED',
  'USER_UPDATED',
  'csv.uploaded',
  'detection.auto_run',
  'detection.run',
  'rule.updated',
  'alert.status_changed',
  'alert.note_added',
  'alert.rescored',
  'alert.severity_raised',
  'customer.viewed',
  'role.permissions_changed',
] as const;
const ACTION_TONE: Record<string, 'success' | 'danger' | 'info' | 'neutral'> = {
  LOGIN_SUCCESS: 'success',
  LOGIN_FAILED: 'danger',
  LOGIN_RATE_LIMITED: 'danger',
  ACCESS_DENIED: 'danger',
  USER_CREATED: 'info',
  USER_UPDATED: 'info',
  'alert.status_changed': 'info',
  'rule.updated': 'info',
};
/** K6: customer views are numerous, so the screen hides them unless asked. */
const VIEW_ACTION = 'customer.viewed';
const DEFAULT_DAYS = 30;

/** E06: alert events can show the decision trace when the user may open the alert. */
function alertTraceId(event: AuditEvent, canViewAlerts: boolean): number | null {
  if (!canViewAlerts || event.entity_type !== 'alert' || !event.action.startsWith('alert.')) return null;
  const id = Number(event.entity_id);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function actionKey(action: string): string {
  return action.replace(/\./g, '_');
}

function isoDaysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** The alerts behind one detection run's R17 event. */
function GroupedRaises({ items, canOpenAlerts }: { items: AuditEvent['grouped']; canOpenAlerts: boolean }) {
  const { t } = useTranslation();
  const severity = (value: unknown) => t(`severity.${String(value) as 'low'}`, { defaultValue: String(value) });
  return (
    <ul className="divide-y divide-border rounded-md bg-surface-muted text-xs">
      {items.map((item) => (
        <li key={item.audit_id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-1.5">
          {canOpenAlerts ? (
            <Link to={`/alerts/${item.entity_id}`} className="font-mono text-info hover:underline">
              alert · {item.entity_id}
            </Link>
          ) : (
            <span className="font-mono">alert · {item.entity_id}</span>
          )}
          <span>
            {t('alertDetail.severityRaised', {
              from: severity(item.details.old),
              to: severity(item.details.new),
              count: Number(item.details.K ?? 0),
            })}
          </span>
        </li>
      ))}
    </ul>
  );
}

interface AuditQuery {
  offset: number;
  limit: number;
  actor_id?: string;
  action?: string;
  exclude_action?: string;
  entity_id?: string;
  date_from?: string;
  date_to?: string;
}

/** GET /audit-log — requires audit:view; filtered and paged on the server (newest first). */
function useAuditLog(query: AuditQuery) {
  return useQuery({
    queryKey: ['audit', query],
    queryFn: ({ signal }) => apiRequest('/audit-log', { query: { ...query }, schema: auditPageSchema, signal }),
    placeholderData: keepPreviousData,
  });
}

export default function AuditLogPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const limit = PAGE_SIZES.find((size) => String(size) === params.get('limit')) ?? 50;
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1);
  const offset = (page - 1) * limit;
  // Filters live in the URL: actor, type (''=all but customer views, 'all', or one action),
  // record (entity_id) and date range (default: last 30 days).
  const actorFilter = params.get('actor') ?? '';
  const typeFilter = params.get('type') ?? '';
  const entityFilter = params.get('entity') ?? '';
  const dateFrom = params.get('from') ?? isoDaysAgo(DEFAULT_DAYS - 1);
  const dateTo = params.get('to') ?? '';
  const [entityDraft, setEntityDraft] = useState(entityFilter);
  const query: AuditQuery = {
    offset,
    limit,
    actor_id: actorFilter || undefined,
    action: typeFilter && typeFilter !== 'all' ? typeFilter : undefined,
    exclude_action: typeFilter === '' ? VIEW_ACTION : undefined,
    entity_id: entityFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const audit = useAuditLog(query);
  // Account list for the actor filter (user:manage only); names in rows come from the API.
  const users = useUsers(can('user:manage'));
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());

  const update = (patch: Record<string, string | null>, keepPage = false) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(patch)) {
          if (value === null || value === '') next.delete(key);
          else next.set(key, value);
        }
        if (!keepPage) next.delete('page');
        return next;
      },
      { replace: true },
    );
  const goTo = (nextPage: number, nextLimit: number = limit) =>
    update({ page: nextPage > 1 ? String(nextPage) : null, limit: nextLimit !== 50 ? String(nextLimit) : null }, true);

  const actorOptions = new Map<string, string>();
  for (const user of users.data ?? []) actorOptions.set(String(user.user_id), user.username);
  for (const event of audit.data?.items ?? []) {
    if (event.actor_id !== null && event.actor_name) actorOptions.set(String(event.actor_id), event.actor_name);
  }
  if (actorFilter && !actorOptions.has(actorFilter)) actorOptions.set(actorFilter, t('audit.unknownActor', { id: actorFilter }));

  const filters = (
    <Card className="mb-4 grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 xl:grid-cols-5">
      <Field label={t('audit.filters.actor')}>
        <Select value={actorFilter} onChange={(event) => update({ actor: event.target.value })}>
          <option value="">{t('audit.filters.all')}</option>
          {[...actorOptions].map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t('audit.filters.type')}>
        <Select value={typeFilter} onChange={(event) => update({ type: event.target.value })}>
          <option value="">{t('audit.filters.allButViews')}</option>
          <option value="all">{t('audit.filters.all')}</option>
          {KNOWN_ACTIONS.map((action) => (
            <option key={action} value={action}>
              {t(`audit.actions.${actionKey(action) as 'LOGIN_SUCCESS'}`)}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t('audit.filters.entity')}>
        <Input
          value={entityDraft}
          maxLength={50}
          placeholder={t('audit.filters.entityPlaceholder')}
          onChange={(event) => setEntityDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') update({ entity: entityDraft.trim() });
          }}
          onBlur={() => update({ entity: entityDraft.trim() })}
        />
      </Field>
      <Field label={t('audit.filters.from')}>
        <Input type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => update({ from: event.target.value || '' })} />
      </Field>
      <Field label={t('audit.filters.to')}>
        <Input type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => update({ to: event.target.value })} />
      </Field>
    </Card>
  );

  const header = <PageHeader breadcrumb={t('audit.breadcrumb')} title={t('nav.audit')} description={t('audit.description')} />;
  if (audit.isPending) return <PageSpinner label={t('common.loading')} />;
  if (audit.isError) {
    return (
      <>
        {header}
        {filters}
        <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />
      </>
    );
  }

  const { total, items } = audit.data;
  const lastPage = Math.max(1, Math.ceil(total / limit));
  const actorName = (event: AuditEvent) => {
    if (event.actor_id === null) return <span className="text-muted">{t('audit.system')}</span>;
    return event.actor_name ?? t('audit.unknownActor', { id: event.actor_id });
  };
  const actionLabel = (action: string) =>
    (KNOWN_ACTIONS as readonly string[]).includes(action) ? t(`audit.actions.${actionKey(action) as 'LOGIN_SUCCESS'}`) : action;

  const toggle = (id: number) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const pager = (
    <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-xs text-muted">
      <p>{total > 0 && t('audit.pageSummary', { total, from: offset + 1, to: offset + items.length })}</p>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2">
          {t('audit.pageSize')}
          <Select className="h-8 w-20" value={limit} onChange={(event) => goTo(1, Number(event.target.value))}>
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </Select>
        </label>
        <Button size="sm" disabled={page <= 1 || audit.isFetching} onClick={() => goTo(page - 1)}>
          <ChevronLeft className="size-3.5" aria-hidden />
          {t('audit.previous')}
        </Button>
        <span className="tabular-nums">
          {page} / {lastPage}
        </span>
        <Button size="sm" disabled={page >= lastPage || audit.isFetching} onClick={() => goTo(page + 1)}>
          {t('audit.next')}
          <ChevronRight className="size-3.5" aria-hidden />
        </Button>
      </div>
    </div>
  );

  return (
    <>
      {header}
      {filters}
      <Card className={cn(audit.isPlaceholderData && 'opacity-70')}>
        {items.length === 0 ? (
          <EmptyState icon={History} title={t('audit.empty')} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-[13px]" aria-label={t('nav.audit')}>
                <thead>
                  <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                    <th scope="col" className="px-5 py-2 font-medium">{t('audit.time')}</th>
                    <th scope="col" className="px-3 py-2 font-medium">{t('audit.actor')}</th>
                    <th scope="col" className="px-3 py-2 font-medium">{t('audit.action')}</th>
                    <th scope="col" className="px-3 py-2 font-medium">{t('audit.entity')}</th>
                    <th scope="col" className="px-5 py-2 font-medium">{t('audit.details')}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((event) => {
                    const expanded = open.has(event.audit_id);
                    const isGroup = event.grouped.length > 0;
                    const traceAlertId = isGroup ? null : alertTraceId(event, can('alert:view'));
                    const hasDetails =
                      isGroup ||
                      traceAlertId !== null ||
                      (event.details !== null && event.details !== undefined && !(typeof event.details === 'object' && Object.keys(event.details).length === 0));
                    return (
                      <Fragment key={event.audit_id}>
                        <tr
                          className={cn(
                            'border-b border-border',
                            expanded && 'border-b-0',
                            // E06: unauthorised attempts stand out as a red row.
                            event.action === 'ACCESS_DENIED' && 'bg-danger-soft',
                          )}
                        >
                          <td className="px-5 py-2.5 whitespace-nowrap text-muted">{formatDateTime(event.created_at, language)}</td>
                          <td className="px-3 py-2.5 font-medium">{actorName(event)}</td>
                          <td className="px-3 py-2.5">
                            <Badge tone={ACTION_TONE[event.action] ?? 'neutral'}>{actionLabel(event.action)}</Badge>
                          </td>
                          <td className="px-3 py-2.5 font-mono text-xs">
                            {event.entity_type}
                            {isGroup ? (
                              <span className="text-muted"> · {t('audit.groupCount', { count: event.grouped.length })}</span>
                            ) : (
                              event.entity_id && <span className="text-muted"> · {event.entity_id}</span>
                            )}
                          </td>
                          <td className="px-5 py-2.5">
                            {hasDetails ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                aria-expanded={expanded}
                                aria-controls={`audit-details-${event.audit_id}`}
                                onClick={() => toggle(event.audit_id)}
                              >
                                {expanded ? t('audit.hideDetails') : t('audit.showDetails')}
                              </Button>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                        </tr>
                        {expanded && (
                          <tr className="border-b border-border">
                            <td colSpan={5} className="px-5 pb-3">
                              <div id={`audit-details-${event.audit_id}`} className={cn(!isGroup && 'grid gap-4 lg:grid-cols-2')}>
                                {isGroup ? (
                                  <GroupedRaises items={event.grouped} canOpenAlerts={can('alert:view')} />
                                ) : (
                                  <>
                                    <pre className="overflow-x-auto rounded-md bg-surface-muted p-3 font-mono text-xs">
                                      {JSON.stringify(event.details, null, 2)}
                                    </pre>
                                    {traceAlertId !== null && <DecisionTrace alertId={traceAlertId} />}
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {pager}
          </>
        )}
      </Card>
    </>
  );
}
