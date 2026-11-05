import type { AlertDetail, AlertHistoryEvent, AlertStatus } from '@/api/schemas/alerts';
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

export type DecisionContextKind = 'escalated' | 'returned' | 'decided';

/**
 * The history event that explains where the alert stands now (E05/E11): the
 * escalation it is waiting on, the return it came back with, or its final decision.
 */
export function decisionContext(
  alert: Pick<AlertDetail, 'status' | 'history'>,
): { kind: DecisionContextKind; event: AlertHistoryEvent } | null {
  const latest = [...alert.history]
    .filter((event) => event.old_status !== event.new_status)
    .sort((a, b) => a.changed_at.localeCompare(b.changed_at))
    .at(-1);
  if (!latest || latest.new_status !== alert.status) return null;
  if (alert.status === 'in_review' && latest.old_status === 'new') return { kind: 'escalated', event: latest };
  if (alert.status === 'new' && latest.old_status === 'in_review') return { kind: 'returned', event: latest };
  if (alert.status === 'closed' || alert.status === 'confirmed_suspicious') return { kind: 'decided', event: latest };
  return null;
}
