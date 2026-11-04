import { useTranslation } from 'react-i18next';
import { StatCard } from '@/components/ui/StatCard';
import { formatNumber } from '@/utils/format';
import { useMySummary } from './api';

export function MySummaryCards() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const summary = useMySummary();
  const data = summary.data;
  const returnedNames = data?.returned_cases.map((item) => item.customer_name).join(', ');
  return (
    <>
      <StatCard
        loading={summary.isPending}
        label={t('alerts.kpiDecidedToday')}
        value={summary.isError ? '—' : data && formatNumber(data.decided_today, language)}
        caption={data && t('alerts.kpiEscalatedToday', { count: data.escalated_today })}
      />
      <StatCard
        loading={summary.isPending}
        label={t('alerts.kpiReturned')}
        value={summary.isError ? '—' : data && formatNumber(data.returned_to_me, language)}
        caption={data && (returnedNames || t('alerts.kpiNoneReturned'))}
        tone={data?.returned_to_me ? 'danger' : 'default'}
      />
    </>
  );
}
