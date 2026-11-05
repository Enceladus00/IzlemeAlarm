import { z } from 'zod';
import { apiDateTime, decimal, pageSchema } from './common';

/*
 * Mirrors backend/api/responses.py (K10). Change both sides together.
 */

export const ALERT_STATUSES = ['new', 'in_review', 'closed', 'confirmed_suspicious'] as const;
export type AlertStatus = (typeof ALERT_STATUSES)[number];

/** Statuses the alert queue can show (open alerts only). */
export const QUEUE_STATUSES = ['new', 'in_review'] as const;
export type QueueStatus = (typeof QUEUE_STATUSES)[number];

export const ALERT_SEVERITIES = ['high', 'medium', 'low'] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];

/** Every decision needs a note (API design 7.14). */
export const NOTE_MAX_LENGTH = 2000;
/** POST /alerts/decisions accepts at most this many alerts. */
export const MAX_DECISION_ALERTS = 50;

/** backend/repositories/alert_repository.py::alert_summary (GET /alerts items) */
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

/** GET /alerts?include_counts=true (E11): the page plus counts per status under the same filters. */
export const alertPageWithCountsSchema = alertPageSchema.extend({
  counts_by_status: z.object({
    new: z.number(),
    in_review: z.number(),
    closed: z.number(),
    confirmed_suspicious: z.number(),
  }),
});
export type AlertPageWithCounts = z.infer<typeof alertPageWithCountsSchema>;

/* ---------------------------------------------------------------- K1 queue */

export const queueEventSchema = z.object({
  old_status: z.string().nullable(),
  new_status: z.string(),
  changed_at: apiDateTime,
  actor_name: z.string().nullable(),
});

export const alertQueueItemSchema = z.object({
  customer_no: z.string(),
  customer_name: z.string(),
  customer_type: z.string().nullable(),
  rule_codes: z.array(z.string()),
  severity: z.enum(['low', 'medium', 'high']),
  max_score: decimal.nullable(),
  alert_count: z.number(),
  transaction_count: z.number(),
  oldest_created_at: apiDateTime,
  escalated_at: apiDateTime.nullable(),
  alert_ids: z.array(z.number()),
  last_event: queueEventSchema.nullable(),
  returned_by: z.string().nullable(),
  returned_note: z.string().nullable(),
  escalated_by: z.string().nullable().optional(),
  escalation_note: z.string().nullable().optional(),
});
export type AlertQueueItem = z.infer<typeof alertQueueItemSchema>;

/** GET /alerts/queue */
export const alertQueueSchema = z.object({
  summary: z.object({
    alerts: z.number(),
    customers: z.number(),
    high_alerts: z.number(),
    high_customers: z.number(),
    returned_customers: z.number(),
  }),
  total: z.number(),
  items: z.array(alertQueueItemSchema),
});
export type AlertQueue = z.infer<typeof alertQueueSchema>;

/* ---------------------------------------------------------- alert detail */

/** A transaction as an analyst sees it: the counterparty is masked on the server (K13). */
export const maskedTransactionSchema = z.object({
  view: z.literal('masked'),
  transaction_id: z.number(),
  tx_time: apiDateTime,
  direction: z.enum(['in', 'out']),
  amount: decimal,
  currency: z.string(),
  channel: z.string(),
  country_code: z.string(),
  counterparty: z.string(),
  counterparty_account: z.string(),
  in_alert: z.boolean(),
});
export type MaskedTransaction = z.infer<typeof maskedTransactionSchema>;

/** Only for customer:view (compliance). */
export const fullAlertTransactionSchema = z.object({
  view: z.literal('full'),
  transaction_id: z.number(),
  transaction_no: z.string(),
  tx_time: apiDateTime,
  direction: z.enum(['in', 'out']),
  amount: decimal,
  currency: z.string(),
  channel: z.string(),
  country_code: z.string(),
  sender_account_no: z.string(),
  sender_customer_no: z.string(),
  sender_customer_name: z.string(),
  receiver_account_no: z.string(),
  receiver_customer_no: z.string(),
  receiver_customer_name: z.string(),
  in_alert: z.boolean(),
});
export type FullAlertTransaction = z.infer<typeof fullAlertTransactionSchema>;

export const alertTransactionSchema = z.discriminatedUnion('view', [
  maskedTransactionSchema,
  fullAlertTransactionSchema,
]);
export type AlertTransaction = z.infer<typeof alertTransactionSchema>;

/** One status change, with who made it. */
export const alertHistoryEventSchema = z.object({
  old_status: z.string().nullable(),
  new_status: z.string(),
  note: z.string().nullable(),
  changed_at: apiDateTime,
  changed_by: z.number(),
  actor_name: z.string().nullable(),
  actor_role: z.string().nullable(),
});
export type AlertHistoryEvent = z.infer<typeof alertHistoryEventSchema>;

/** System changes to the alert (K9 rescoring, R17 severity raise). */
export const alertSystemEventSchema = z.object({
  action: z.string(),
  created_at: apiDateTime,
  details: z.record(z.string(), z.unknown()),
});
export type AlertSystemEvent = z.infer<typeof alertSystemEventSchema>;

export const explanationStepSchema = z.object({
  step: z.number(),
  text: z.string(),
  status: z.string(),
  details: z.record(z.string(), z.unknown()),
});
export type ExplanationStep = z.infer<typeof explanationStepSchema>;

/** K8 "Why was this triggered?" */
export const explanationSchema = z.object({
  rule_code: z.string(),
  rule_name: z.string(),
  alert_mode: z.string(),
  customer_type: z.string().nullable(),
  parameter_status: z.string(),
  raw_x: decimal.nullable(),
  score: decimal.nullable(),
  x_esik: z.string().nullable(),
  x_kesin: z.string().nullable(),
  parameters: z.record(z.string(), z.unknown()),
  steps: z.array(explanationStepSchema),
  run: z.object({ run_id: z.string(), as_of: apiDateTime }),
});
export type Explanation = z.infer<typeof explanationSchema>;

/** GET /alerts/{id} */
export const alertDetailSchema = z.object({
  alert_id: z.number(),
  rule_code: z.string(),
  rule_name: z.string(),
  customer_no: z.string(),
  customer_name: z.string(),
  customer: z.object({
    customer_no: z.string(),
    customer_name: z.string(),
    customer_type: z.string().nullable(),
  }),
  severity: z.string(),
  score: decimal.nullable(),
  status: z.string(),
  created_at: apiDateTime,
  transaction_count: z.number(),
  transaction_ids: z.array(z.number()),
  transactions: z.array(alertTransactionSchema),
  history: z.array(alertHistoryEventSchema),
  escalated_by: z
    .object({ user_id: z.number(), actor_name: z.string().nullable(), changed_at: apiDateTime })
    .nullable(),
  explanation: explanationSchema.nullable(),
  events: z.array(alertSystemEventSchema),
});
export type AlertDetail = z.infer<typeof alertDetailSchema>;

/** PATCH /alerts/{id}/status */
export const alertStatusResultSchema = z.object({
  alert_id: z.number(),
  status: z.string(),
  changed: z.boolean(),
});

/** POST /alerts/decisions */
export const decisionResultSchema = z.object({
  decision_id: z.string(),
  status: z.string(),
  alert_ids: z.array(z.number()),
  decided_at: apiDateTime,
});
export type DecisionResult = z.infer<typeof decisionResultSchema>;

/* ------------------------------------------------------- K4 customer context */

/** GET /alerts/{id}/customer-context */
export const customerContextSchema = z.object({
  alert_id: z.number(),
  period_start: apiDateTime,
  profile: z.object({
    customer_type: z.string().nullable(),
    occupation: z.string().nullable(),
    monthly_income: decimal.nullable(),
    risk_level: z.string().nullable(),
    customer_since: z.number().nullable(),
  }),
  accounts: z.array(z.object({ account: z.string(), currency: z.string(), type: z.string().nullable() })),
  summary: z.array(
    z.object({
      currency: z.string(),
      incoming_30d: decimal,
      outgoing_30d: decimal,
      avg_monthly_outgoing_6m: decimal,
    }),
  ),
  transactions: z.array(maskedTransactionSchema),
  truncated: z.boolean(),
});
export type CustomerContext = z.infer<typeof customerContextSchema>;

/** GET /alerts/rule-codes */
export const ruleCodesSchema = z.array(z.string());

/** Natural order: R01 … R18, S1, S2, then legacy R1 … R4. */
export function compareRuleCodes(a: string, b: string): number {
  const legacyA = /^R\d$/.test(a);
  const legacyB = /^R\d$/.test(b);
  if (legacyA !== legacyB) return legacyA ? 1 : -1;
  return a.localeCompare(b, 'en', { numeric: true });
}
