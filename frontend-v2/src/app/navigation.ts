import {
  Activity,
  BellRing,
  FlaskConical,
  GitBranch,
  History,
  LayoutDashboard,
  SlidersHorizontal,
  Upload,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { hasAnyPermission, type Permission, type PermissionSet } from '@/auth/permissions';
import type { Translation } from '@/i18n/locales/tr';

export type NavSection = keyof Translation['nav']['sections'];
export type NavId =
  | 'detectionOverview'
  | 'alerts'
  | 'transactions'
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
  /** Permission that unlocks editing; without it the item is marked read-only. */
  editPermission?: Permission;
}

/**
 * Mirrors the permission checks in frontend/app.py (Streamlit). This is only a
 * usability aid: every endpoint enforces its own permission on the server.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { id: 'detectionOverview', path: '/overview', section: 'monitoring', icon: LayoutDashboard, anyOf: ['dashboard:view'] },
  { id: 'alerts', path: '/alerts', section: 'monitoring', icon: BellRing, anyOf: ['alert:view'], editPermission: 'alert:update' },
  { id: 'transactions', path: '/transactions', section: 'monitoring', icon: GitBranch, anyOf: ['customer:view'] },
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
  return item.editPermission !== undefined && !permissions.has(item.editPermission);
}

export function visibleNavItems(permissions: PermissionSet): NavItem[] {
  return NAV_ITEMS.filter((item) => canOpen(item, permissions));
}

/** The first screen the user may open, used as the landing page. */
export function homePath(permissions: PermissionSet): string | null {
  return visibleNavItems(permissions)[0]?.path ?? null;
}
