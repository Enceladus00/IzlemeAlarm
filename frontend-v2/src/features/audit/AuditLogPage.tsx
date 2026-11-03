import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, History } from 'lucide-react';
import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';
import { apiRequest } from '@/api/client';
import { auditPageSchema, type AuditEvent } from '@/api/schemas/users';
import { useAuth } from '@/auth/auth-context';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { PageSpinner } from '@/components/ui/Spinner';
import { useUsers } from '@/features/users/api';
import { cn } from '@/utils/cn';
import { formatDateTime } from '@/utils/format';

const PAGE_SIZES = [50, 100, 200] as const;
const KNOWN_ACTIONS = ['LOGIN_SUCCESS', 'LOGIN_FAILED', 'ACCESS_DENIED', 'USER_CREATED', 'USER_UPDATED'] as const;
const ACTION_TONE: Record<string, 'success' | 'danger' | 'info' | 'neutral'> = {
  LOGIN_SUCCESS: 'success',
  LOGIN_FAILED: 'danger',
  ACCESS_DENIED: 'danger',
  USER_CREATED: 'info',
  USER_UPDATED: 'info',
};

/** GET /audit-log — requires audit:view; paged on the server (newest first). */
function useAuditLog(offset: number, limit: number) {
  return useQuery({
    queryKey: ['audit', offset, limit],
    queryFn: ({ signal }) => apiRequest('/audit-log', { query: { offset, limit }, schema: auditPageSchema, signal }),
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
  const audit = useAuditLog(offset, limit);
  // Usernames come from /users, which needs user:manage; otherwise show the id.
  const users = useUsers(can('user:manage'));
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());

  const goTo = (nextPage: number, nextLimit: number = limit) =>
    setParams(
      () => {
        const next = new URLSearchParams();
        if (nextPage > 1) next.set('page', String(nextPage));
        if (nextLimit !== 50) next.set('limit', String(nextLimit));
        return next;
      },
      { replace: true },
    );

  const header = <PageHeader breadcrumb={t('audit.breadcrumb')} title={t('nav.audit')} description={t('audit.description')} />;
  if (audit.isPending) return <PageSpinner label={t('common.loading')} />;
  if (audit.isError) {
    return (
      <>
        {header}
        <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />
      </>
    );
  }

  const { total, items } = audit.data;
  const lastPage = Math.max(1, Math.ceil(total / limit));
  const actorName = (event: AuditEvent) => {
    if (event.actor_id === null) return <span className="text-muted">{t('audit.system')}</span>;
    const user = users.data?.find((candidate) => candidate.user_id === event.actor_id);
    return user ? user.username : t('audit.unknownActor', { id: event.actor_id });
  };
  const actionLabel = (action: string) =>
    (KNOWN_ACTIONS as readonly string[]).includes(action) ? t(`audit.actions.${action as 'LOGIN_SUCCESS'}`) : action;

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
                    const hasDetails = event.details !== null && event.details !== undefined && !(typeof event.details === 'object' && Object.keys(event.details).length === 0);
                    return (
                      <Fragment key={event.audit_id}>
                        <tr className={cn('border-b border-border', expanded && 'border-b-0')}>
                          <td className="px-5 py-2.5 whitespace-nowrap text-muted">{formatDateTime(event.created_at, language)}</td>
                          <td className="px-3 py-2.5 font-medium">{actorName(event)}</td>
                          <td className="px-3 py-2.5">
                            <Badge tone={ACTION_TONE[event.action] ?? 'neutral'}>{actionLabel(event.action)}</Badge>
                          </td>
                          <td className="px-3 py-2.5 font-mono text-xs">
                            {event.entity_type}
                            {event.entity_id && <span className="text-muted"> · {event.entity_id}</span>}
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
                              <pre id={`audit-details-${event.audit_id}`} className="overflow-x-auto rounded-md bg-surface-muted p-3 font-mono text-xs">
                                {JSON.stringify(event.details, null, 2)}
                              </pre>
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
