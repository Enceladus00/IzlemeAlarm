import { Compass } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <Card>
      <EmptyState
        icon={Compass}
        title={t('pages.notFoundTitle')}
        action={
          <Link to="/" className="text-sm font-semibold text-info underline underline-offset-2">
            {t('common.backToHome')}
          </Link>
        }
      >
        {t('pages.notFoundBody')}
      </EmptyState>
    </Card>
  );
}
