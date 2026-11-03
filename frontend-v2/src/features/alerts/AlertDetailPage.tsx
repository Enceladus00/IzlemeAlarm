import { ArrowLeft, ExternalLink, History, SearchX } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useParams } from 'react-router';
import type { AlertDetail, AlertHistoryEvent } from '@/api/schemas/alerts';
import { useAuth } from '@/auth/auth-context';
import { TransactionTable } from '@/components/TransactionTable';
import { AlertStatusBadge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { PageHeader } from '@/components/ui/PageHeader';
import { Placeholder } from '@/components/ui/Placeholder';
import { PageSpinner } from '@/components/ui/Spinner';
import { ApiError } from '@/api/client';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';
import { useAlertCustomerHistory, useAlertDetail, useCustomerAlerts } from './api';
import { StatusUpdateForm } from './StatusUpdateForm';

const KNOWN_STATUSES = ['new', 'in_review', 'closed', 'confirmed_suspicious'];

export default function AlertDetailPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { alertId: rawId } = useParams();
  const alertId = Number(rawId);
  const location = useLocation();
  const backSearch = (location.state as { backSearch?: string } | null)?.backSearch ?? '';
  const { can } = useAuth();
  const detail = useAlertDetail(alertId);
  const siblings = useCustomerAlerts(detail.data?.customer_no);

  const backLink = (
    <Link to={`/alerts${backSearch}`} className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-info hover:underline">
      <ArrowLeft className="size-4" aria-hidden />
      {t('alertDetail.backToQueue')}
    </Link>
  );

  if (detail.isPending) return <PageSpinner label={t('common.loading')} />;
  if (detail.isError) {
    const notFound = detail.error instanceof ApiError && detail.error.kind === 'notFound';
    return (
      <>
        <div className="mb-4">{backLink}</div>
        {notFound ? (
          <Card>
            <EmptyState icon={SearchX} title={t('alertDetail.notFound')}>
              {t('alertDetail.notFoundBody')}
            </EmptyState>
          </Card>
        ) : (
          <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
        )}
      </>
    );
  }

  const alert = detail.data;
  return (
    <>
      <div className="mb-3">{backLink}</div>
      <PageHeader
        breadcrumb={`${t('alerts.breadcrumb')} / #${alert.alert_id}`}
        title={`${t('alertDetail.title', { id: alert.alert_id })} · ${alert.rule_code} ${alert.rule_name}`}
        actions={
          <div className="flex items-center gap-2">
            <SeverityBadge severity={alert.severity} />
            <AlertStatusBadge status={alert.status} />
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 p-5 text-[13px] sm:grid-cols-3 lg:grid-cols-5">
              <SummaryItem label={t('alertDetail.customer')}>
                <span className="font-semibold">{alert.customer_name}</span>
                <span className="block font-mono text-xs text-muted">{alert.customer_no}</span>
              </SummaryItem>
              <SummaryItem label={t('alertDetail.rule')}>
                <span className="font-mono font-semibold">{alert.rule_code}</span>
                <span className="block text-xs text-muted">{alert.rule_name}</span>
              </SummaryItem>
              <SummaryItem label={t('alertDetail.score')}>
                <span className="font-mono">
                  {alert.score === null
                    ? '—'
                    : formatNumber(alert.score, language, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                </span>
              </SummaryItem>
              <SummaryItem label={t('alertDetail.created')}>{formatDateTime(alert.created_at, language)}</SummaryItem>
              <SummaryItem label={t('alertDetail.transactionCount')}>
                {formatNumber(alert.transaction_count, language)}
              </SummaryItem>
            </dl>
          </Card>

          <Card>
            <CardHeader title={t('alertDetail.linkedTransactions')} />
            <div className="px-2 pt-3 pb-3">
              <TransactionTable
                transactions={alert.transactions}
                label={t('alertDetail.linkedTransactions')}
                focusCustomerNo={alert.customer_no}
              />
            </div>
          </Card>

          <CustomerHistoryCard alert={alert} />
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title={t('alertDetail.updateTitle')} />
            <div className="p-5">
              {can('alert:update') ? (
                <StatusUpdateForm alertId={alert.alert_id} currentStatus={alert.status} />
              ) : (
                <InlineAlert tone="info">{t('alertDetail.readOnly')}</InlineAlert>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title={t('alertDetail.history')} />
            <div className="p-5">
              <HistoryTimeline events={alert.history} />
            </div>
          </Card>

          <Card>
            <CardHeader
              title={t('alertDetail.otherAlerts')}
              description={siblings.data && t('alertDetail.otherAlertsCount', { count: siblings.data.total })}
            />
            <div className="p-3">
              {siblings.isError ? (
                <ErrorState error={siblings.error} onRetry={() => void siblings.refetch()} />
              ) : !siblings.data ? (
                <div className="h-24 animate-pulse rounded bg-neutral-soft" aria-hidden />
              ) : (
                <ul className="space-y-1">
                  {siblings.data.items.map((item) => {
                    const current = item.alert_id === alert.alert_id;
                    return (
                      <li key={item.alert_id}>
                        <Link
                          to={`/alerts/${item.alert_id}`}
                          state={{ backSearch }}
                          aria-current={current ? 'page' : undefined}
                          className={cn(
                            'flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md px-2.5 py-2 text-[13px] hover:bg-surface-hover',
                            current && 'bg-accent-soft ring-1 ring-accent/50',
                          )}
                        >
                          <span className="font-mono text-muted">#{item.alert_id}</span>
                          <span className="font-mono font-semibold">{item.rule_code}</span>
                          <span className="ml-auto flex gap-1.5">
                            <SeverityBadge severity={item.severity} />
                            <AlertStatusBadge status={item.status} />
                          </span>
                          <span className="w-full text-xs text-muted">{formatDateTime(item.created_at, language)}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function SummaryItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="mb-1 text-xs text-muted">{label}</dt>
      <dd className="break-words">{children}</dd>
    </div>
  );
}

function statusLabel(t: ReturnType<typeof useTranslation>['t'], status: string | null): string {
  if (!status) return '—';
  return KNOWN_STATUSES.includes(status) ? t(`alertStatus.${status as 'new'}`) : status;
}

function HistoryTimeline({ events }: { events: AlertHistoryEvent[] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  if (events.length === 0) {
    return <EmptyState icon={History} title={t('alertDetail.historyEmpty')} className="py-6" />;
  }
  const ordered = [...events].sort((a, b) => b.changed_at.localeCompare(a.changed_at));
  return (
    <ol className="relative space-y-4 border-l border-border pl-5">
      {ordered.map((event, index) => {
        const title =
          event.old_status === null
            ? t('alertDetail.historyCreated', { status: statusLabel(t, event.new_status) })
            : event.old_status === event.new_status
              ? t('alertDetail.historyNoteOnly')
              : t('alertDetail.historyChange', { from: statusLabel(t, event.old_status), to: statusLabel(t, event.new_status) });
        return (
          <li key={`${event.changed_at}-${index}`} className="relative">
            <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-surface bg-series-1" aria-hidden />
            <p className="text-[13px] font-semibold">{title}</p>
            <p className="text-xs text-muted">
              {formatDateTime(event.changed_at, language)} · {t('alertDetail.historyActor')}: <Placeholder className="py-0 text-[11px]" />
            </p>
            {event.note && <p className="mt-1.5 rounded-md bg-surface-muted px-3 py-2 text-[13px] whitespace-pre-wrap">{event.note}</p>}
          </li>
        );
      })}
    </ol>
  );
}

function CustomerHistoryCard({ alert }: { alert: AlertDetail }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [requested, setRequested] = useState(false);
  const history = useAlertCustomerHistory(alert.alert_id, requested);

  return (
    <Card>
      <CardHeader
        title={t('alertDetail.customerHistory')}
        description={t('alertDetail.customerHistoryHint')}
        actions={
          can('customer:view') && (
            <Link
              to={`/transactions?customer=${encodeURIComponent(alert.customer_no)}`}
              className="inline-flex items-center gap-1 text-[13px] font-semibold text-info hover:underline"
            >
              {t('alertDetail.openInAnalysis')}
              <ExternalLink className="size-3.5" aria-hidden />
            </Link>
          )
        }
      />
      <div className="px-2 pt-3 pb-3">
        {!requested ? (
          <div className="px-3 pb-2">
            <Button onClick={() => setRequested(true)}>{t('alertDetail.loadCustomerHistory')}</Button>
          </div>
        ) : history.isError ? (
          <div className="px-3">
            <ErrorState error={history.error} onRetry={() => void history.refetch()} />
          </div>
        ) : !history.data ? (
          <div className="mx-3 h-32 animate-pulse rounded bg-neutral-soft" aria-hidden />
        ) : (
          <TransactionTable
            transactions={history.data.items}
            label={t('alertDetail.customerHistory')}
            focusCustomerNo={alert.customer_no}
          />
        )}
      </div>
    </Card>
  );
}
