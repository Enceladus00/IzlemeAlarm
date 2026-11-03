import { Construction } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { NavItem } from '@/app/navigation';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHeader } from '@/components/ui/PageHeader';

/** Stand-in for screens that later milestones will implement. */
export default function ComingSoonPage({ item }: { item: NavItem }) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader breadcrumb={t(`nav.sections.${item.section}`)} title={t(`nav.${item.id}`)} />
      <Card>
        <EmptyState icon={Construction} title={t('pages.comingSoonTitle')}>
          {t('pages.comingSoonBody')}
        </EmptyState>
      </Card>
    </>
  );
}
