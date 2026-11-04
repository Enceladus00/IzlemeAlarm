import { ArrowDownLeft, ArrowUpRight, Flag } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { MaskedTransaction } from '@/api/schemas/alerts';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatDateTime, formatMoney } from '@/utils/format';

const CHANNELS = ['atm', 'mobile', 'internet', 'branch'] as const;

/**
 * Transfers seen from the alert customer's side. The counterparty name and account
 * arrive already masked from the server ("Ö. Kılıç", "…7781").
 */
export function MaskedTransactionTable({
  transactions,
  label,
  showAlertFlag = false,
}: {
  transactions: MaskedTransaction[];
  label: string;
  showAlertFlag?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  if (transactions.length === 0) return <EmptyState title={t('transactionsTable.empty')} className="py-8" />;
  const channelLabel = (channel: string) =>
    (CHANNELS as readonly string[]).includes(channel) ? t(`transactionsTable.channels.${channel as 'atm'}`) : channel;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-[13px]" aria-label={label}>
        <thead>
          <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.time')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.direction')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('transactionsTable.amount')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.counterparty')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.counterpartyAccount')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.country')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.channel')}</th>
            {showAlertFlag && (
              <th scope="col" className="px-3 py-2 font-medium">
                <span className="sr-only">{t('transactionsTable.inAlert')}</span>
                <Flag className="size-3.5" aria-hidden />
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => (
            <tr key={tx.transaction_id} className="border-b border-border last:border-0">
              <td className="px-3 py-2 whitespace-nowrap">{formatDateTime(tx.tx_time, language)}</td>
              <td className="px-3 py-2">
                {tx.direction === 'out' ? (
                  <span className="inline-flex items-center gap-1 text-danger">
                    <ArrowUpRight className="size-3.5" aria-hidden />
                    {t('transactionsTable.outgoing')}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-success">
                    <ArrowDownLeft className="size-3.5" aria-hidden />
                    {t('transactionsTable.incoming')}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-right font-mono whitespace-nowrap">
                {formatMoney(tx.amount, tx.currency, language)}
              </td>
              <td className="px-3 py-2">{tx.counterparty}</td>
              <td className="px-3 py-2 font-mono text-xs">{tx.counterparty_account}</td>
              <td className="px-3 py-2 font-mono text-xs">{tx.country_code}</td>
              <td className="px-3 py-2">{channelLabel(tx.channel)}</td>
              {showAlertFlag && (
                <td className="px-3 py-2">
                  {tx.in_alert && <Flag className="size-3.5 text-danger" aria-label={t('transactionsTable.inAlert')} />}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
