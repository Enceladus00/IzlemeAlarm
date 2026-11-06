import { z } from 'zod';
import { apiDateTime } from './common';

/** GET /dashboard/summary (backend/services/analysis_service.py::dashboard_summary). */
export const dashboardSummarySchema = z.object({
  days: z.number(),
  customers: z.number(),
  accounts: z.number(),
  transactions: z.number(),
  alerts: z.number(),
  suspicious_transactions: z.number(),
  by_status: z.record(z.string(), z.number()),
  by_severity: z.record(z.string(), z.number()),
  by_rule: z.record(z.string(), z.number()),
  trends: z.array(
    z.object({
      date: z.string(),
      alerts: z.number(),
      suspicious_transactions: z.number(),
    }),
  ),
});
export type DashboardSummary = z.infer<typeof dashboardSummarySchema>;

const recordMetricSchema = z.object({
  total: z.number(),
  added_last_7_days: z.number(),
  last_added_at: apiDateTime.nullable(),
});

/** GET /admin/system-overview (analysis_service.py::system_overview). */
export const systemOverviewSchema = z.object({
  health: z.object({
    api: z.string(),
    database: z.string(),
    database_latency_ms: z.number(),
    schema_revision: z.string().nullable(),
    /** Newest migration known to the API code; equal to schema_revision when up to date. */
    schema_head: z.string().nullable(),
  }),
  rules: z.object({
    active: z.number(),
    last_run_at: apiDateTime.nullable(),
    last_run_status: z.string().nullable(),
    last_run_duration_ms: z.number().nullable(),
  }),
  records: z.object({
    customers: recordMetricSchema,
    accounts: recordMetricSchema,
    transactions: recordMetricSchema,
    alerts: recordMetricSchema,
  }),
  security: z.object({
    session_ttl_seconds: z.number(),
    demo_endpoint_enabled: z.boolean(),
    active_users: z.number(),
    total_users: z.number(),
    csv_max_bytes: z.number(),
    csv_max_rows: z.number(),
    failed_logins_last_24h: z.number(),
    access_denied_last_24h: z.number(),
  }),
});
export type SystemOverview = z.infer<typeof systemOverviewSchema>;

/** GET /health (public). */
export const healthSchema = z.object({ status: z.string(), database: z.string() });

/** GET /dashboard/my-summary (backend/api/responses.py::MySummary) */
export const mySummarySchema = z.object({
  decided_today: z.number(),
  escalated_today: z.number(),
  returned_to_me: z.number(),
  returned_cases: z.array(
    z.object({
      customer_no: z.string(),
      customer_name: z.string(),
      rule_codes: z.array(z.string()),
      alert_ids: z.array(z.number()),
      returned_by: z.string().nullable(),
      returned_at: z.string(),
      note: z.string().nullable(),
    }),
  ),
  /** E08 "Panelim": queue = the shared analyst queue (status new). */
  queue_pending: z.number(),
  queue_high: z.number(),
  closed_today: z.number(),
  escalated_today_confirmed: z.number(),
  escalations_30d: z.number(),
  /** Current status of the alerts I escalated in the last 30 days; sums to escalations_30d. */
  escalation_outcome_30d: z.object({ confirmed: z.number(), closed: z.number(), returned: z.number(), pending: z.number() }),
  decisions_today: z.array(
    z.object({
      alert_id: z.number(),
      customer_no: z.string(),
      customer_name: z.string(),
      rule_code: z.string(),
      severity: z.enum(['low', 'medium', 'high']),
      old_status: z.string().nullable(),
      new_status: z.string(),
      changed_at: z.string(),
      note: z.string().nullable(),
    }),
  ),
});
export type MySummary = z.infer<typeof mySummarySchema>;

/** GET /dashboard/funnel (K3 tab 2). created = analyst_closed + analyst_open + escalated. */
export const dashboardFunnelSchema = z.object({
  days: z.number(),
  created: z.number(),
  /** E10 KPIs: open = status new or in_review; rates 0–1, null when nothing to divide. */
  open: z.number(),
  confirmed: z.number(),
  escalation_rate: z.number().nullable(),
  confirmed_rate: z.number().nullable(),
  avg_decision_days: z.number().nullable(),
  analyst_closed: z.number(),
  analyst_open: z.number(),
  escalated: z.number(),
  escalation_outcome: z.object({
    confirmed: z.number(),
    closed: z.number(),
    returned: z.number(),
    pending: z.number(),
  }),
});
export type DashboardFunnel = z.infer<typeof dashboardFunnelSchema>;

/** GET /dashboard/rule-performance (K3 tab 3). */
export const rulePerformanceSchema = z.array(
  z.object({
    rule_code: z.string(),
    name: z.string(),
    is_active: z.boolean(),
    evaluated: z.number(),
    alerts: z.number(),
    avg_alert_score: z.union([z.string(), z.number()]).transform(String).nullable(),
    confirmed: z.number(),
    closed: z.number(),
    hit_rate: z.number().nullable(),
    provisional: z.boolean(),
  }),
);
export type RulePerformance = z.infer<typeof rulePerformanceSchema>;
