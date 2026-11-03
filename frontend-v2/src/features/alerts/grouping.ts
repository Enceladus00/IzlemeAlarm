import { compareRuleCodes, type AlertSummary } from '@/api/schemas/alerts';
import { parseApiDate } from '@/utils/format';

export const SEVERITY_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

export interface CustomerGroup {
  customerNo: string;
  customerName: string;
  /** Highest severity first, then oldest first. */
  alerts: AlertSummary[];
  ruleCodes: string[];
  maxSeverity: string;
  oldestCreatedAt: string;
  ageDays: number;
}

/** Whole calendar days between the alert's local date and today (0 = today). */
export function ageInDays(createdAt: string, now: Date): number {
  const created = parseApiDate(createdAt);
  if (!created) return 0;
  const startOfCreated = new Date(created.getFullYear(), created.getMonth(), created.getDate());
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.max(0, Math.round((startOfToday.getTime() - startOfCreated.getTime()) / 86_400_000));
}

function compareAlerts(a: AlertSummary, b: AlertSummary): number {
  return (
    (SEVERITY_RANK[b.severity] ?? 0) - (SEVERITY_RANK[a.severity] ?? 0) ||
    a.created_at.localeCompare(b.created_at) ||
    a.alert_id - b.alert_id
  );
}

/**
 * One row per customer, sorted by highest severity, then by the age of the
 * customer's oldest alert (oldest first) — the order in the design.
 */
export function groupAlertsByCustomer(alerts: AlertSummary[], now: Date): CustomerGroup[] {
  const byCustomer = new Map<string, AlertSummary[]>();
  for (const alert of alerts) {
    const list = byCustomer.get(alert.customer_no);
    if (list) list.push(alert);
    else byCustomer.set(alert.customer_no, [alert]);
  }

  const groups: CustomerGroup[] = [];
  for (const [customerNo, list] of byCustomer) {
    const sorted = [...list].sort(compareAlerts);
    const oldest = list.reduce((min, alert) => (alert.created_at < min ? alert.created_at : min), list[0]!.created_at);
    groups.push({
      customerNo,
      customerName: list[0]!.customer_name,
      alerts: sorted,
      ruleCodes: [...new Set(list.map((alert) => alert.rule_code))].sort(compareRuleCodes),
      maxSeverity: sorted[0]!.severity,
      oldestCreatedAt: oldest,
      ageDays: ageInDays(oldest, now),
    });
  }

  return groups.sort(
    (a, b) =>
      (SEVERITY_RANK[b.maxSeverity] ?? 0) - (SEVERITY_RANK[a.maxSeverity] ?? 0) ||
      a.oldestCreatedAt.localeCompare(b.oldestCreatedAt) ||
      a.customerName.localeCompare(b.customerName, 'tr'),
  );
}

/** Case- and dotted-i-insensitive substring match on customer number or name. */
export function matchesSearch(group: CustomerGroup, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase('tr-TR');
  if (!needle) return true;
  return (
    group.customerNo.toLocaleLowerCase('tr-TR').includes(needle) ||
    group.customerName.toLocaleLowerCase('tr-TR').includes(needle)
  );
}
