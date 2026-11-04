import { ArrowLeft, History, SearchX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useParams } from 'react-router';
import type {
  AlertDetail,
  AlertHistoryEvent,
  AlertSystemEvent,
  FullAlertTransaction,
  MaskedTransaction,
} from '@/api/schemas/alerts';
import type { Transaction } from '@/api/schemas/transactions';
import { TransactionTable } from '@/components/TransactionTable';
import { AlertStatusBadge, SeverityBadge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';
import { PageSpinner } from '@/components/ui/Spinner';
import { ApiError } from '@/api/client';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';
import { useAlertDetail, useCustomerAlerts } from './api';
import { CustomerContextCard } from './CustomerContextCard';
import { ExplanationPanel } from './ExplanationPanel';
import { MaskedTransactionTable } from './MaskedTransactionTable';
import { StatusUpdateForm } from './StatusUpdateForm';

const KNOWN_STATUSES = ['new', 'in_review', 'closed', 'confirmed_suspicious'];

export default function AlertDetailPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { alertId: rawId } = useParams();
  const alertId = Number(rawId);
  const location = useLocation();
  const backSearch = (location.state as { backSearch?: string } | null)?.backSearch ?? '';
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
                <span className="block font-mono text-xs text-muted">
                  {alert.customer_no}
                  {alert.customer.customer_type && (
                    <span className="font-sans">
                      {' · '}
                      {t(`customerType.${alert.customer.customer_type as 'BIREYSEL'}`, {
                        defaultValue: alert.customer.customer_type,
                      })}
                    </span>
                  )}
                </span>
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

          <ExplanationPanel explanation={alert.explanation} />

          <Card>
            <CardHeader title={t('alertDetail.linkedTransactions')} />
            <div className="px-2 pt-3 pb-3">
              <LinkedTransactions alert={alert} />
            </div>
          </Card>

          <CustomerContextCard alert={alert} />
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title={t('alertDetail.updateTitle')} />
            <div className="p-5">
              <StatusUpdateForm alert={alert} backSearch={backSearch} />
            </div>
          </Card>

          <Card>
            <CardHeader title={t('alertDetail.history')} />
            <div className="p-5">
              <HistoryTimeline events={alert.history} systemEvents={alert.events} />
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

type StatusKey = 'alertStatus.new' | 'alertStatus.in_review' | 'alertStatus.closed' | 'alertStatus.confirmed_suspicious';

function statusLabel(translate: (key: StatusKey) => string, status: string | null): string {
  if (!status) return '—';
  return KNOWN_STATUSES.includes(status) ? translate(`alertStatus.${status}` as StatusKey) : status;
}

type TimelineEntry =
  | { kind: 'status'; at: string; event: AlertHistoryEvent }
  | { kind: 'system'; at: string; event: AlertSystemEvent };

function HistoryTimeline({ events, systemEvents }: { events: AlertHistoryEvent[]; systemEvents: AlertSystemEvent[] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const entries: TimelineEntry[] = [
    ...events.map((event): TimelineEntry => ({ kind: 'status', at: event.changed_at, event })),
    ...systemEvents.map((event): TimelineEntry => ({ kind: 'system', at: event.created_at, event })),
  ];
  if (entries.length === 0) {
    return <EmptyState icon={History} title={t('alertDetail.historyEmpty')} className="py-6" />;
  }
  const ordered = entries.sort((a, b) => b.at.localeCompare(a.at));
  return (
    <ol className="relative space-y-4 border-l border-border pl-5">
      {ordered.map((entry, index) => {
        if (entry.kind === 'system') {
          const details = entry.event.details;
          const severity = (value: unknown) =>
            t(`severity.${String(value) as 'low'}`, { defaultValue: String(value) });
          const title =
            entry.event.action === 'alert.severity_raised'
              ? t('alertDetail.severityRaised', {
                  from: severity(details.old),
                  to: severity(details.new),
                  count: Number(details.K ?? 0),
                })
              : t('alertDetail.rescored', {
                  from: formatNumber(String(details.old_score ?? '0'), language, { maximumFractionDigits: 4 }),
                  to: formatNumber(String(details.new_score ?? '0'), language, { maximumFractionDigits: 4 }),
                });
          return (
            <li key={`system-${entry.at}-${index}`} className="relative">
              <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-surface bg-series-2" aria-hidden />
              <p className="text-[13px] font-semibold">{title}</p>
              <p className="text-xs text-muted">
                {formatDateTime(entry.at, language)} · {t('alertDetail.system')}
              </p>
            </li>
          );
        }
        const event = entry.event;
        const title =
          event.old_status === null
            ? t('alertDetail.historyCreated', { status: statusLabel((key) => t(key), event.new_status) })
            : t('alertDetail.historyChange', { from: statusLabel((key) => t(key), event.old_status), to: statusLabel((key) => t(key), event.new_status) });
        const role = event.actor_role
          ? t(`roles.${event.actor_role as 'analyst'}`, { defaultValue: event.actor_role })
          : null;
        return (
          <li key={`${event.changed_at}-${index}`} className="relative">
            <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-surface bg-series-1" aria-hidden />
            <p className="text-[13px] font-semibold">{title}</p>
            <p className="text-xs text-muted">
              {formatDateTime(event.changed_at, language)} · {t('alertDetail.historyActor')}: {event.actor_name ?? '—'}
              {role && ` (${role})`}
            </p>
            {event.note && <p className="mt-1.5 rounded-md bg-surface-muted px-3 py-2 text-[13px] whitespace-pre-wrap">{event.note}</p>}
          </li>
        );
      })}
    </ol>
  );
}

/** Masked rows for analysts (K13); full rows only for customer:view. */
function LinkedTransactions({ alert }: { alert: AlertDetail }) {
  const { t } = useTranslation();
  const masked = alert.transactions.filter((tx): tx is MaskedTransaction => tx.view === 'masked');
  const full = alert.transactions.filter((tx): tx is FullAlertTransaction => tx.view === 'full');
  if (full.length > 0) {
    const rows: Transaction[] = full.map((tx) => ({
      transaction_id: tx.transaction_id,
      transaction_no: tx.transaction_no,
      amount: tx.amount,
      currency: tx.currency,
      tx_time: tx.tx_time,
      country_code: tx.country_code,
      channel: tx.channel,
      sender_account_no: tx.sender_account_no,
      sender_customer_no: tx.sender_customer_no,
      sender_customer_name: tx.sender_customer_name,
      receiver_account_no: tx.receiver_account_no,
      receiver_customer_no: tx.receiver_customer_no,
      receiver_customer_name: tx.receiver_customer_name,
    }));
    return (
      <TransactionTable transactions={rows} label={t('alertDetail.linkedTransactions')} focusCustomerNo={alert.customer_no} />
    );
  }
  return <MaskedTransactionTable transactions={masked} label={t('alertDetail.linkedTransactions')} />;
}
