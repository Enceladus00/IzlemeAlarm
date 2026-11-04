import { ExternalLink, Lock } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ApiError } from '@/api/client';
import type { AlertDetail } from '@/api/schemas/alerts';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { ErrorState } from '@/components/ui/ErrorState';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { formatDate, formatMoney } from '@/utils/format';
import { useCustomerContext } from './api';
import { MaskedTransactionTable } from './MaskedTransactionTable';

/**
 * K4: the alert customer's profile and last six months, masked on the server.
 * Opening it is logged as a customer view (K6), so it loads only on request.
 * Analysts may open it only while the alert is new.
 */
export function CustomerContextCard({ alert }: { alert: AlertDetail }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { can } = useAuth();
  const [requested, setRequested] = useState(false);
  const allowed = alert.status === 'new' || can('alert:confirm');
  const context = useCustomerContext(alert.alert_id, requested && allowed);
  const closedForAnalyst =
    !allowed || (context.error instanceof ApiError && context.error.kind === 'forbidden');

  return (
    <Card>
      <CardHeader
        title={t('customerContext.title')}
        description={t('customerContext.hint')}
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
      <div className="space-y-4 p-5">
        {closedForAnalyst ? (
          <InlineAlert tone="info">
            <span className="inline-flex items-center gap-1.5">
              <Lock className="size-3.5" aria-hidden />
              {t('customerContext.closed')}
            </span>
          </InlineAlert>
        ) : !requested ? (
          <div className="space-y-2">
            <p className="text-xs text-muted">{t('customerContext.logged')}</p>
            <Button onClick={() => setRequested(true)}>{t('customerContext.load')}</Button>
          </div>
        ) : context.isError ? (
          <ErrorState error={context.error} onRetry={() => void context.refetch()} />
        ) : !context.data ? (
          <div className="h-32 animate-pulse rounded bg-neutral-soft" aria-hidden />
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-3">
              <Item label={t('customerContext.type')}>
                {context.data.profile.customer_type ? t(`customerType.${context.data.profile.customer_type as 'BIREYSEL'}`) : '—'}
              </Item>
              <Item label={t('customerContext.occupation')}>{context.data.profile.occupation ?? '—'}</Item>
              <Item label={t('customerContext.income')}>
                {context.data.profile.monthly_income === null
                  ? '—'
                  : formatMoney(context.data.profile.monthly_income, 'TRY', language)}
              </Item>
              <Item label={t('customerContext.risk')}>
                {context.data.profile.risk_level ? t(`customerContext.riskLevels.${context.data.profile.risk_level as 'low'}`, { defaultValue: context.data.profile.risk_level }) : '—'}
              </Item>
              <Item label={t('customerContext.since')}>{context.data.profile.customer_since ?? '—'}</Item>
              <Item label={t('customerContext.accounts')}>
                {context.data.accounts.length === 0
                  ? '—'
                  : context.data.accounts.map((account) => `${account.account} · ${account.currency}`).join(', ')}
              </Item>
            </dl>

            {context.data.summary.length > 0 && (
              <table className="w-full text-[13px]" aria-label={t('customerContext.summaryTitle')}>
                <thead>
                  <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                    <th scope="col" className="py-1.5 font-medium">{t('customerContext.currency')}</th>
                    <th scope="col" className="py-1.5 text-right font-medium">{t('customerContext.incoming30')}</th>
                    <th scope="col" className="py-1.5 text-right font-medium">{t('customerContext.outgoing30')}</th>
                    <th scope="col" className="py-1.5 text-right font-medium">{t('customerContext.avgOutgoing')}</th>
                  </tr>
                </thead>
                <tbody>
                  {context.data.summary.map((row) => (
                    <tr key={row.currency} className="border-b border-border last:border-0">
                      <td className="py-1.5 font-mono">{row.currency}</td>
                      <td className="py-1.5 text-right font-mono">{formatMoney(row.incoming_30d, row.currency, language)}</td>
                      <td className="py-1.5 text-right font-mono">{formatMoney(row.outgoing_30d, row.currency, language)}</td>
                      <td className="py-1.5 text-right font-mono">
                        {formatMoney(row.avg_monthly_outgoing_6m, row.currency, language)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <p className="text-xs text-muted">
              {t('customerContext.period', { from: formatDate(context.data.period_start, language) })}
            </p>
            <MaskedTransactionTable
              transactions={context.data.transactions}
              label={t('customerContext.transactions')}
              showAlertFlag
            />
            {context.data.truncated && <InlineAlert tone="info">{t('customerContext.truncated')}</InlineAlert>}
          </>
        )}
      </div>
    </Card>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="mb-0.5 text-xs text-muted">{label}</dt>
      <dd className="break-words">{children}</dd>
    </div>
  );
}
