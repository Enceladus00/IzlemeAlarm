import { z } from 'zod';
import { apiDateTime } from './common';

/** GET /dashboard/summary (backend/services/analysis_service.py::dashboard_summary). */
export const dashboardSummarySchema = z.object({
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
