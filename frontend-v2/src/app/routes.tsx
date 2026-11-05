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

const DetectionOverview = lazy(() => import('@/features/detection-overview/DetectionOverviewPage'));
const SystemOverview = lazy(() => import('@/features/system-overview/SystemOverviewPage'));
const AlertQueue = lazy(() => import('@/features/alerts/AlertQueuePage'));
const AlertDetail = lazy(() => import('@/features/alerts/AlertDetailPage'));
const AllAlerts = lazy(() => import('@/features/alerts/AllAlertsPage'));
const Customers = lazy(() => import('@/features/customers/CustomersPage'));
const CustomerDetail = lazy(() => import('@/features/customers/CustomerDetailPage'));
const TransactionAnalysis = lazy(() => import('@/features/transactions/TransactionAnalysisPage'));
const DataManagement = lazy(() => import('@/features/data-management/DataManagementPage'));
const DemoLab = lazy(() => import('@/features/demo-lab/DemoLabPage'));
const Rules = lazy(() => import('@/features/rules/RulesPage'));
const Users = lazy(() => import('@/features/users/UsersPage'));
const AuditLog = lazy(() => import('@/features/audit/AuditLogPage'));

/**
 * Screen implementations by navigation id.
 */
const PAGES: Record<NavId, PageComponent> = {
  detectionOverview: DetectionOverview,
  alerts: AlertQueue,
  allAlerts: AllAlerts,
  transactions: TransactionAnalysis,
  customers: Customers,
  dataManagement: DataManagement,
  demoLab: DemoLab,
  rules: Rules,
  systemOverview: SystemOverview,
  users: Users,
  audit: AuditLog,
};

/** Nested screens that share a navigation item (and its permission). */
const SUB_ROUTES: Array<{ path: string; parent: NavId; page: PageComponent }> = [
  { path: 'alerts/:alertId', parent: 'alerts', page: AlertDetail },
  { path: 'customers/:customerNo', parent: 'customers', page: CustomerDetail },
];

function PageFallback() {
  const { t } = useTranslation();
  return <PageSpinner label={t('common.loading')} />;
}

function guarded(item: NavItem, Page: PageComponent): RouteObject['element'] {
  return (
    <RequirePermission item={item}>
      <Suspense fallback={<PageFallback />}>
        <Page item={item} />
      </Suspense>
    </RequirePermission>
  );
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
      ...NAV_ITEMS.map((item): RouteObject => ({ path: item.path.slice(1), element: guarded(item, PAGES[item.id]) })),
      ...SUB_ROUTES.map(({ path, parent, page }): RouteObject => ({
        path,
        element: guarded(NAV_ITEMS.find((item) => item.id === parent)!, page),
      })),
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];
