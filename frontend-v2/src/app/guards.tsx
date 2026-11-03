import { ShieldOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router';
import { useAuth } from '@/auth/auth-context';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageSpinner } from '@/components/ui/Spinner';
import { canOpen, homePath, type NavItem } from './navigation';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, profileError, retryProfile } = useAuth();
  const location = useLocation();
  const { t } = useTranslation();

  if (status === 'checking') return <PageSpinner label={t('auth.loadingProfile')} />;
  if (status === 'profileError') {
    return (
      <div className="mx-auto max-w-lg p-6">
        <ErrorState error={profileError} onRetry={retryProfile} />
      </div>
    );
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

export function RequirePermission({ item, children }: { item: NavItem; children: ReactNode }) {
  const { permissions } = useAuth();
  const { t } = useTranslation();
  if (!canOpen(item, permissions)) {
    return (
      <Card>
        <EmptyState icon={ShieldOff} title={t('pages.forbiddenTitle')}>
          {t('pages.forbiddenBody', { permission: item.anyOf.join(' / ') })}
        </EmptyState>
      </Card>
    );
  }
  return <>{children}</>;
}

/** Index route: send the user to the first screen they are allowed to open. */
export function HomeRedirect() {
  const { permissions } = useAuth();
  const { t } = useTranslation();
  const target = homePath(permissions);
  if (target) return <Navigate to={target} replace />;
  return (
    <Card>
      <EmptyState icon={ShieldOff} title={t('auth.noPermissions')} />
    </Card>
  );
}
