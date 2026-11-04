import type { AlertPage } from '@/api/schemas/alerts';
import type { DashboardSummary, SystemOverview } from '@/api/schemas/dashboard';

/** Mirrors the real wire format, including Decimal values serialized as strings. */
function trendDays(): DashboardSummary['trends'] {
  const days: DashboardSummary['trends'] = [];
  const start = new Date(2026, 9, 5);
  for (let index = 0; index < 30; index += 1) {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
    days.push({ date: iso, alerts: index % 5, suspicious_transactions: (index * 3) % 7 });
  }
  return days;
}

export const dashboardFixture: DashboardSummary = {
  days: 30,
  customers: 1284,
  accounts: 2317,
  transactions: 186420,
  alerts: 3912,
  suspicious_transactions: 4790,
  by_status: { new: 12, in_review: 5, closed: 3800, confirmed_suspicious: 95 },
  by_severity: { high: 6, medium: 4, low: 2 },
  by_rule: { R01: 40, R05: 120, R10: 7, R14: 0, R1: 0 },
  trends: trendDays(),
};

export const emptyDashboardFixture: DashboardSummary = {
  days: 30,
  customers: 0,
  accounts: 0,
  transactions: 0,
  alerts: 0,
  suspicious_transactions: 0,
  by_status: {},
  by_severity: {},
  by_rule: { R01: 0, R02: 0 },
  trends: trendDays().map((row) => ({ ...row, alerts: 0, suspicious_transactions: 0 })),
};

export const latestAlertsFixture: AlertPage = {
  total: 2,
  items: [
    {
      alert_id: 5531,
      rule_code: 'R02',
      rule_name: 'Large single transaction',
      customer_no: 'C-1042',
      customer_name: 'Ahmet Yılmaz',
      severity: 'high',
      score: '0.9400',
      status: 'new',
      created_at: '2026-10-26T16:40:00',
      transaction_count: 1,
      transaction_ids: [91],
    },
    {
      alert_id: 5524,
      rule_code: 'R01',
      rule_name: 'Near-limit activity',
      customer_no: 'C-0311',
      customer_name: 'Kaya Tekstil Ltd. Şti.',
      severity: 'medium',
      score: null,
      status: 'in_review',
      created_at: '2026-10-26T15:03:00',
      transaction_count: 2,
      transaction_ids: [88, 89],
    },
  ],
};

export const systemOverviewFixture: SystemOverview = {
  health: { api: 'ok', database: 'connected', database_latency_ms: 2.1, schema_revision: '0006_alert_workflow', schema_head: '0006_alert_workflow' },
  rules: { active: 18, last_run_at: '2026-10-29T18:42:00', last_run_status: 'completed', last_run_duration_ms: 2400 },
  records: {
    customers: { total: 1284, added_last_7_days: 96, last_added_at: '2026-10-29T18:21:00' },
    accounts: { total: 2317, added_last_7_days: 214, last_added_at: null },
    transactions: { total: 186420, added_last_7_days: 4790, last_added_at: '2026-10-29T18:42:00' },
    alerts: { total: 3912, added_last_7_days: 178, last_added_at: '2026-10-29T18:43:00' },
  },
  security: {
    session_ttl_seconds: 1800,
    demo_endpoint_enabled: false,
    active_users: 4,
    total_users: 5,
    csv_max_bytes: 5 * 1024 * 1024,
    csv_max_rows: 5000,
    failed_logins_last_24h: 3,
    access_denied_last_24h: 1,
  },
};
