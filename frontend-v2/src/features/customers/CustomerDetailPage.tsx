import { ArrowLeft, ExternalLink, SearchX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/auth-context';
import { AlertStatusBadge, Badge, SeverityBadge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';
import { PageSpinner } from '@/components/ui/Spinner';
import { useCustomerAlerts } from '@/features/alerts/api';
import { formatDate, formatDateTime, formatMoney, formatNumber } from '@/utils/format';
import { useCustomerProfile } from './api';
import { CustomerAnalysis } from './CustomerAnalysis';

/** Full customer profile (GET /customers/{no}); opening it is written to the audit log. */
export default function CustomerDetailPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { customerNo = '' } = useParams();
  const { can } = useAuth();
  const profile = useCustomerProfile(customerNo);
  const alerts = useCustomerAlerts(customerNo, undefined, can('alert:view') && profile.isSuccess);

  const back = (
    <Link to="/customers" className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-info hover:underline">
      <ArrowLeft className="size-4" aria-hidden />
      {t('customers.back')}
    </Link>
  );

  if (profile.isPending) return <PageSpinner label={t('common.loading')} />;
  if (profile.isError) {
    const notFound = profile.error instanceof ApiError && profile.error.kind === 'notFound';
    return (
      <>
        <div className="mb-4">{back}</div>
        {notFound ? (
          <Card>
            <EmptyState icon={SearchX} title={t('customers.notFound')} />
          </Card>
        ) : (
          <ErrorState error={profile.error} onRetry={() => void profile.refetch()} />
        )}
      </>
    );
  }

  const data = profile.data;
  const fact = (label: string, value: React.ReactNode) => (
    <div className="min-w-0">
      <dt className="mb-0.5 text-xs text-muted">{label}</dt>
      <dd className="break-words">{value ?? '—'}</dd>
    </div>
  );

  return (
    <>
      <div className="mb-3">{back}</div>
      <PageHeader
        breadcrumb={`${t('nav.customers')} / ${data.customer_no}`}
        title={data.full_name}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={data.is_active ? 'success' : 'neutral'}>{data.is_active ? t('customers.active') : t('customers.inactive')}</Badge>
            <Link
              to={`/transactions?customer=${encodeURIComponent(data.customer_no)}`}
              className="inline-flex items-center gap-1 text-[13px] font-semibold text-info hover:underline"
            >
              {t('alertDetail.openInAnalysis')}
              <ExternalLink className="size-3.5" aria-hidden />
            </Link>
          </div>
        }
      />
      <p className="mb-4 text-xs text-muted">{t('customers.profileLogged')}</p>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title={t('customers.profile')} />
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 px-5 pb-5 text-[13px] sm:grid-cols-3">
            {fact(t('customers.customerNo'), <span className="font-mono">{data.customer_no}</span>)}
            {fact(t('customers.type'), data.customer_type && t(`customerType.${data.customer_type as 'BIREYSEL'}`, { defaultValue: data.customer_type }))}
            {fact(t('customerContext.occupation'), data.occupation)}
            {fact(t('customerContext.income'), data.monthly_income === null ? null : formatMoney(data.monthly_income, 'TRY', language))}
            {fact(t('customers.risk'), data.risk_level && t(`customerContext.riskLevels.${data.risk_level as 'low'}`, { defaultValue: data.risk_level }))}
            {fact(t('customers.since'), data.created_at && formatDate(data.created_at, language))}
          </dl>
        </Card>
        <Card>
          <CardHeader title={t('customers.alertsTitle')} description={t('customers.alertCounts', { open: data.alerts.open, total: data.alerts.total })} />
          <div className="px-3 pb-3">
            {!can('alert:view') ? (
              <p className="px-2 text-[13px] text-muted">{t('customers.alertsNoPermission')}</p>
            ) : !alerts.data ? (
              <div className="h-20 animate-pulse rounded bg-neutral-soft" aria-hidden />
            ) : alerts.data.items.length === 0 ? (
              <p className="px-2 text-[13px] text-muted">{t('customers.noAlerts')}</p>
            ) : (
              <ul className="space-y-1">
                {alerts.data.items.map((alert) => (
                  <li key={alert.alert_id}>
                    <Link
                      to={`/alerts/${alert.alert_id}`}
                      className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md px-2.5 py-2 text-[13px] hover:bg-surface-hover"
                    >
                      <span className="font-mono text-muted">#{alert.alert_id}</span>
                      <span className="font-mono font-semibold">{alert.rule_code}</span>
                      <span className="ml-auto flex gap-1.5">
                        <SeverityBadge severity={alert.severity} />
                        <AlertStatusBadge status={alert.status} />
                      </span>
                      <span className="w-full text-xs text-muted">{formatDateTime(alert.created_at, language)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader title={t('customers.accountsTitle')} />
        <div className="overflow-x-auto px-2 pb-3">
          <table className="w-full min-w-[640px] text-[13px]" aria-label={t('customers.accountsTitle')}>
            <thead>
              <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                <th scope="col" className="px-3 py-2 font-medium">{t('customers.columns.account')}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t('customers.currency')}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t('customers.columns.accountType')}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t('customers.columns.opened')}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">{t('customers.columns.transactions')}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t('customers.columns.status')}</th>
              </tr>
            </thead>
            <tbody>
              {data.accounts.map((account) => (
                <tr key={account.account_no} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-mono text-xs">
                    <Link
                      to={`/transactions?customer=${encodeURIComponent(data.customer_no)}&focus=${encodeURIComponent(`account:${account.account_no}`)}`}
                      className="text-info hover:underline"
                    >
                      {account.account_no}
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-mono">{account.currency}</td>
                  <td className="px-3 py-2">{account.account_type ?? '—'}</td>
                  <td className="px-3 py-2">{account.opened_at ? formatDate(account.opened_at, language) : '—'}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(account.transaction_count, language)}</td>
                  <td className="px-3 py-2">
                    <Badge tone={account.is_active ? 'success' : 'neutral'}>{account.is_active ? t('customers.active') : t('customers.inactive')}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.accounts.length === 0 && <p className="px-3 py-4 text-[13px] text-muted">{t('customers.noAccounts')}</p>}
        </div>
      </Card>

      <CustomerAnalysis customerNo={data.customer_no} />
    </>
  );
}
