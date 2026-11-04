import type { AlertStatus } from '@/api/schemas/alerts';
import type { Permission, PermissionSet } from '@/auth/permissions';

/**
 * Mirrors backend/services/alert_workflow.py (API design 7.1). The server is the
 * authority; the UI only offers what the server would accept.
 */
export interface Transition {
  from: AlertStatus;
  to: AlertStatus;
  permission: Permission;
  /** i18n key under alertDetail.decisions */
  label: 'closeFalsePositive' | 'escalate' | 'confirm' | 'closeExplained' | 'returnToAnalyst';
  /** i18n key under alertDetail.decided (ALR040–043) */
  success: 'escalated' | 'closed' | 'confirmed' | 'returned';
}

export const TRANSITIONS: readonly Transition[] = [
  { from: 'new', to: 'closed', permission: 'alert:update', label: 'closeFalsePositive', success: 'closed' },
  { from: 'new', to: 'in_review', permission: 'alert:escalate', label: 'escalate', success: 'escalated' },
  { from: 'in_review', to: 'confirmed_suspicious', permission: 'alert:confirm', label: 'confirm', success: 'confirmed' },
  { from: 'in_review', to: 'closed', permission: 'alert:confirm', label: 'closeExplained', success: 'closed' },
  { from: 'in_review', to: 'new', permission: 'alert:confirm', label: 'returnToAnalyst', success: 'returned' },
];

/** Leaving in_review towards one of these is a final decision: four eyes applies. */
export const FOUR_EYES_TARGETS: readonly AlertStatus[] = ['confirmed_suspicious', 'closed'];

export function availableTransitions(current: string, permissions: PermissionSet): Transition[] {
  return TRANSITIONS.filter((item) => item.from === current && permissions.has(item.permission));
}

/** A user who can decide on escalated alerts but not escalate is a compliance officer. */
export function isComplianceUser(permissions: PermissionSet): boolean {
  return permissions.has('alert:confirm') && !permissions.has('alert:escalate');
}
