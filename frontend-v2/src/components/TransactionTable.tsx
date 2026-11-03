import { ArrowDownLeft, ArrowUpRight, Flag } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Transaction } from '@/api/schemas/transactions';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatDateTime, formatMoney } from '@/utils/format';

const CHANNELS = ['atm', 'mobile', 'internet', 'branch'] as const;

/**
 * Shared transfer table. With `focusCustomerNo`, each row shows whether the
 * transfer is incoming or outgoing for that customer.
 */
export function TransactionTable({
  transactions,
  label,
  focusCustomerNo,
  showAlertLinked = false,
}: {
  transactions: Transaction[];
  label: string;
  focusCustomerNo?: string;
  showAlertLinked?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  if (transactions.length === 0) return <EmptyState title={t('transactionsTable.empty')} className="py-8" />;

  const channelLabel = (channel: string) =>
    (CHANNELS as readonly string[]).includes(channel) ? t(`transactionsTable.channels.${channel as 'atm'}`) : channel;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-[13px]" aria-label={label}>
        <thead>
          <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.transaction')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.time')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('transactionsTable.amount')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.from')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.to')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.country')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('transactionsTable.channel')}</th>
            {showAlertLinked && (
              <th scope="col" className="px-3 py-2 font-medium">
                <span className="sr-only">{t('transactionsTable.alertLinked')}</span>
                <Flag className="size-3.5" aria-hidden />
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => {
            const outgoing = focusCustomerNo !== undefined && tx.sender_customer_no === focusCustomerNo;
            const incoming = focusCustomerNo !== undefined && tx.receiver_customer_no === focusCustomerNo;
            return (
              <tr key={tx.transaction_id} className="border-b border-border last:border-0">
                <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
                  <span className="inline-flex items-center gap-1.5">
                    {outgoing && (
                      <ArrowUpRight className="size-3.5 text-danger" aria-label={t('transactionsTable.outgoing')} />
                    )}
                    {incoming && !outgoing && (
                      <ArrowDownLeft className="size-3.5 text-success" aria-label={t('transactionsTable.incoming')} />
                    )}
                    {tx.transaction_no}
                  </span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-muted">{formatDateTime(tx.tx_time, language)}</td>
                <td className="px-3 py-2 text-right font-mono whitespace-nowrap tabular-nums">
                  {formatMoney(tx.amount, tx.currency, language)}
                </td>
                <td className="px-3 py-2">
                  <p className="font-medium">{tx.sender_customer_name}</p>
                  <p className="font-mono text-xs text-muted">{tx.sender_account_no}</p>
                </td>
                <td className="px-3 py-2">
                  <p className="font-medium">{tx.receiver_customer_name}</p>
                  <p className="font-mono text-xs text-muted">{tx.receiver_account_no}</p>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{tx.country_code}</td>
                <td className="px-3 py-2">{channelLabel(tx.channel)}</td>
                {showAlertLinked && (
                  <td className="px-3 py-2">
                    {tx.alert_linked && (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-danger">
                        <Flag className="size-3.5" aria-hidden />
                        <span className="sr-only">{t('transactionsTable.alertLinked')}</span>
                      </span>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
