import { z } from 'zod';
import { apiDateTime, decimal, pageSchema } from './common';
import { transactionSchema } from './transactions';

export const ALERT_STATUSES = ['new', 'in_review', 'closed', 'confirmed_suspicious'] as const;
export type AlertStatus = (typeof ALERT_STATUSES)[number];

export const ALERT_SEVERITIES = ['high', 'medium', 'low'] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];

/** Statuses the API refuses without an analyst note (alert_service.py::update_status). */
export const NOTE_REQUIRED_STATUSES: readonly string[] = ['closed', 'confirmed_suspicious'];
export const NOTE_MAX_LENGTH = 2000;

/** backend/repositories/alert_repository.py::alert_summary */
export const alertSummarySchema = z.object({
  alert_id: z.number(),
  rule_code: z.string(),
  rule_name: z.string(),
  customer_no: z.string(),
  customer_name: z.string(),
  severity: z.string(),
  score: decimal.nullable(),
  status: z.string(),
  created_at: apiDateTime,
  transaction_count: z.number(),
  transaction_ids: z.array(z.number()),
});
export type AlertSummary = z.infer<typeof alertSummarySchema>;

/** GET /alerts */
export const alertPageSchema = pageSchema(alertSummarySchema);
export type AlertPage = z.infer<typeof alertPageSchema>;

/** One status change / note. The API does not say who made the change. */
export const alertHistoryEventSchema = z.object({
  old_status: z.string().nullable(),
  new_status: z.string(),
  note: z.string().nullable(),
  changed_at: apiDateTime,
});
export type AlertHistoryEvent = z.infer<typeof alertHistoryEventSchema>;

/** GET /alerts/{id} */
export const alertDetailSchema = alertSummarySchema.extend({
  transactions: z.array(transactionSchema),
  history: z.array(alertHistoryEventSchema),
});
export type AlertDetail = z.infer<typeof alertDetailSchema>;

/** PATCH /alerts/{id}/status */
export const alertStatusResultSchema = z.object({
  alert_id: z.number(),
  status: z.string(),
  changed: z.boolean(),
});

/** GET /alerts/rule-codes */
export const ruleCodesSchema = z.array(z.string());

/** Natural order: R01, R02 … R15, then legacy R1 … R4. */
export function compareRuleCodes(a: string, b: string): number {
  const legacyA = /^R\d$/.test(a);
  const legacyB = /^R\d$/.test(b);
  if (legacyA !== legacyB) return legacyA ? 1 : -1;
  return a.localeCompare(b, 'en', { numeric: true });
}
