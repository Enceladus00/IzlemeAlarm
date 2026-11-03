import { lazy, Suspense, type ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import type { RouteObject } from 'react-router';
import { LoginPage } from '@/auth/LoginPage';
import { PageSpinner } from '@/components/ui/Spinner';
import { AppShell } from './AppShell';
import { HomeRedirect, RequireAuth, RequirePermission } from './guards';
import { NAV_ITEMS, type NavId, type NavItem } from './navigation';
import { NotFoundPage } from './NotFoundPage';

type PageComponent = ComponentType<{ item: NavItem }>;

const ComingSoon = lazy(() => import('@/features/placeholder/ComingSoonPage'));
const DetectionOverview = lazy(() => import('@/features/detection-overview/DetectionOverviewPage'));
const SystemOverview = lazy(() => import('@/features/system-overview/SystemOverviewPage'));

/**
 * Screen implementations by navigation id. Milestones replace the
 * ComingSoon entries with the real feature pages.
 */
const PAGES: Record<NavId, PageComponent> = {
  detectionOverview: DetectionOverview,
  alerts: ComingSoon,
  transactions: ComingSoon,
  dataManagement: ComingSoon,
  demoLab: ComingSoon,
  rules: ComingSoon,
  systemOverview: SystemOverview,
  users: ComingSoon,
  audit: ComingSoon,
};

function PageFallback() {
  const { t } = useTranslation();
  return <PageSpinner label={t('common.loading')} />;
}

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <HomeRedirect /> },
      ...NAV_ITEMS.map((item): RouteObject => {
        const Page = PAGES[item.id];
        return {
          path: item.path.slice(1),
          element: (
            <RequirePermission item={item}>
              <Suspense fallback={<PageFallback />}>
                <Page item={item} />
              </Suspense>
            </RequirePermission>
          ),
        };
      }),
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];
