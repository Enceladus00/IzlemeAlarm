import { z } from 'zod';
import { apiDateTime, decimal, pageSchema } from './common';

export const ALERT_STATUSES = ['new', 'in_review', 'closed', 'confirmed_suspicious'] as const;
export type AlertStatus = (typeof ALERT_STATUSES)[number];

export const ALERT_SEVERITIES = ['high', 'medium', 'low'] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];

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
