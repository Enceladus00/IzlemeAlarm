import {
  Activity,
  BellRing,
  ListChecks,
  Contact,
  FlaskConical,
  GitBranch,
  History,
  LayoutDashboard,
  SlidersHorizontal,
  UserRound,
  Upload,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { hasAnyPermission, type Permission, type PermissionSet } from '@/auth/permissions';
import type { Translation } from '@/i18n/locales/tr';

export type NavSection = keyof Translation['nav']['sections'];
export type NavId =
  | 'myPanel'
  | 'detectionOverview'
  | 'alerts'
  | 'allAlerts'
  | 'transactions'
  | 'customers'
  | 'dataManagement'
  | 'demoLab'
  | 'rules'
  | 'systemOverview'
  | 'users'
  | 'audit';

export interface NavItem {
  id: NavId;
  path: string;
  section: NavSection;
  icon: LucideIcon;
  /** The user needs at least one of these to see and open the screen. */
  anyOf: readonly Permission[];
  /** Permissions that unlock editing; without any of them the item is marked read-only. */
  editPermission?: Permission | readonly Permission[];
}

/**
 * Mirrors the permission checks in frontend/app.py (Streamlit). This is only a
 * usability aid: every endpoint enforces its own permission on the server.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  // E08: the analyst's own day; first so analysts land here.
  { id: 'myPanel', path: '/my-panel', section: 'monitoring', icon: UserRound, anyOf: ['alert:escalate'] },
  { id: 'detectionOverview', path: '/overview', section: 'monitoring', icon: LayoutDashboard, anyOf: ['dashboard:view'] },
  { id: 'alerts', path: '/alerts', section: 'monitoring', icon: BellRing, anyOf: ['alert:view'], editPermission: ['alert:update', 'alert:escalate', 'alert:confirm'] },
  // E11: every alert in any status — a compliance screen (analysts work from their queue).
  { id: 'allAlerts', path: '/all-alerts', section: 'monitoring', icon: ListChecks, anyOf: ['alert:confirm'] },
  { id: 'transactions', path: '/transactions', section: 'monitoring', icon: GitBranch, anyOf: ['customer:view'] },
  { id: 'customers', path: '/customers', section: 'monitoring', icon: Contact, anyOf: ['customer:view'] },
  { id: 'dataManagement', path: '/data', section: 'operations', icon: Upload, anyOf: ['upload:create', 'upload:view'] },
  { id: 'demoLab', path: '/demo', section: 'operations', icon: FlaskConical, anyOf: ['dashboard:view'] },
  { id: 'rules', path: '/rules', section: 'operations', icon: SlidersHorizontal, anyOf: ['rule:view'], editPermission: 'rule:edit' },
  { id: 'systemOverview', path: '/system', section: 'administration', icon: Activity, anyOf: ['user:manage'] },
  { id: 'users', path: '/users', section: 'administration', icon: Users, anyOf: ['user:manage'] },
  { id: 'audit', path: '/audit', section: 'administration', icon: History, anyOf: ['audit:view'] },
];

export const NAV_SECTIONS: readonly NavSection[] = ['monitoring', 'operations', 'administration'];

export function canOpen(item: NavItem, permissions: PermissionSet): boolean {
  return hasAnyPermission(permissions, item.anyOf);
}

export function isReadOnly(item: NavItem, permissions: PermissionSet): boolean {
  if (item.editPermission === undefined) return false;
  const required: readonly Permission[] =
    typeof item.editPermission === 'string' ? [item.editPermission] : item.editPermission;
  return !hasAnyPermission(permissions, required);
}

export function visibleNavItems(permissions: PermissionSet): NavItem[] {
  return NAV_ITEMS.filter((item) => canOpen(item, permissions));
}

/** The first screen the user may open, used as the landing page. */
export function homePath(permissions: PermissionSet): string | null {
  return visibleNavItems(permissions)[0]?.path ?? null;
}
