import { http, HttpResponse } from 'msw';
import type {
  AlertDetail,
  AlertHistoryEvent,
  AlertQueueItem,
  AlertSummary,
  CustomerContext,
  MaskedTransaction,
} from '@/api/schemas/alerts';
import type { Transaction } from '@/api/schemas/transactions';
import { API } from './server';

/** Naive ISO timestamp `days` ago at the given hour (local time, like the API). */
export function daysAgo(days: number, hour = 10): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  date.setHours(hour, 12, 0, 0);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
}

let nextId = 5500;
export function makeAlert(partial: Partial<AlertSummary> & Pick<AlertSummary, 'customer_no' | 'customer_name'>): AlertSummary {
  nextId += 1;
  return {
    alert_id: nextId,
    rule_code: 'R01',
    rule_name: 'Near-limit activity',
    severity: 'medium',
    score: '0.6500',
    status: 'new',
    created_at: daysAgo(1),
    transaction_count: 1,
    transaction_ids: [1],
    ...partial,
  };
}

export const queueAlerts: AlertSummary[] = [
  makeAlert({ alert_id: 5518, customer_no: 'C-1042', customer_name: 'Ahmet Yılmaz', rule_code: 'R03', rule_name: 'Ortalamadan sapma', severity: 'high', created_at: daysAgo(4, 14) }),
  makeAlert({ alert_id: 5524, customer_no: 'C-1042', customer_name: 'Ahmet Yılmaz', rule_code: 'R01', rule_name: 'Limite yakın tekrar', severity: 'medium', transaction_count: 2, created_at: daysAgo(4, 15) }),
  makeAlert({ alert_id: 5531, customer_no: 'C-1042', customer_name: 'Ahmet Yılmaz', rule_code: 'R02', rule_name: 'Hızlı para çıkışı', severity: 'low', score: '0.9400', created_at: daysAgo(4, 16) }),
  makeAlert({ alert_id: 5540, customer_no: 'C-0311', customer_name: 'Kaya Tekstil Ltd. Şti.', rule_code: 'R04', severity: 'high', created_at: daysAgo(3) }),
  makeAlert({ alert_id: 5541, customer_no: 'C-0311', customer_name: 'Kaya Tekstil Ltd. Şti.', rule_code: 'R01', severity: 'medium', created_at: daysAgo(2) }),
  makeAlert({ alert_id: 5550, customer_no: 'C-2290', customer_name: 'Selin Arslan', rule_code: 'R03', severity: 'high', created_at: daysAgo(1) }),
  makeAlert({ alert_id: 5560, customer_no: 'C-0877', customer_name: 'Mert Demir', rule_code: 'R02', severity: 'medium', created_at: daysAgo(2) }),
  makeAlert({ alert_id: 5570, customer_no: 'C-0154', customer_name: 'Burak Aydın', rule_code: 'R01', severity: 'low', created_at: daysAgo(0) }),
  makeAlert({ alert_id: 5580, customer_no: 'C-0154', customer_name: 'Burak Aydın', rule_code: 'R01', severity: 'low', status: 'closed', created_at: daysAgo(9) }),
  makeAlert({ alert_id: 5590, customer_no: 'C-0777', customer_name: 'Deniz Kurt', rule_code: 'R05', severity: 'high', status: 'in_review', created_at: daysAgo(6) }),
];

const CUSTOMER_TYPES: Record<string, string> = { 'C-0311': 'KURUMSAL' };
const RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

/** Records each GET /alerts and GET /alerts/queue query so tests can assert what the UI asked for. */
export const alertRequests: URLSearchParams[] = [];
export const queueRequests: URLSearchParams[] = [];

/**
 * GET /alerts (filters + paging, newest first) and GET /alerts/queue (grouped by
 * customer, sorted by severity → oldest alert → customer no), like the API.
 */
export function alertsHandler(dataset: AlertSummary[] = queueAlerts, returned: Record<string, string> = {}) {
  return [
    http.get(`${API}/alerts/queue`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      queueRequests.push(params);
      const status = params.get('status') ?? 'new';
      const q = (params.get('q') ?? '').toLocaleLowerCase('tr-TR');
      const filtered = dataset
        .filter((alert) => alert.status === status)
        .filter((alert) => !params.get('severity') || alert.severity === params.get('severity'))
        .filter((alert) => !params.get('rule_code') || alert.rule_code === params.get('rule_code'))
        .filter(
          (alert) =>
            !q ||
            alert.customer_name.toLocaleLowerCase('tr-TR').includes(q) ||
            alert.customer_no.toLocaleLowerCase('tr-TR').includes(q),
        );
      const groups = new Map<string, AlertSummary[]>();
      for (const alert of filtered) groups.set(alert.customer_no, [...(groups.get(alert.customer_no) ?? []), alert]);
      const items: AlertQueueItem[] = [...groups.values()].map((alerts) => {
        const sorted = [...alerts].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.alert_id - b.alert_id);
        const first = sorted[0]!;
        const severity = [...alerts].sort((a, b) => (RANK[b.severity] ?? 0) - (RANK[a.severity] ?? 0))[0]!.severity;
        return {
          customer_no: first.customer_no,
          customer_name: first.customer_name,
          customer_type: CUSTOMER_TYPES[first.customer_no] ?? 'BIREYSEL',
          rule_codes: [...new Set(alerts.map((alert) => alert.rule_code))].sort(),
          severity: severity as AlertQueueItem['severity'],
          max_score: alerts.map((alert) => alert.score ?? '0').sort().at(-1)!,
          alert_count: alerts.length,
          transaction_count: alerts.reduce((sum, alert) => sum + alert.transaction_count, 0),
          oldest_created_at: first.created_at,
          escalated_at: status === 'in_review' ? first.created_at : null,
          alert_ids: sorted.map((alert) => alert.alert_id),
          last_event: null,
          returned_by: returned[first.customer_no] ?? null,
          returned_note: returned[first.customer_no] ? 'Eksik belge' : null,
        };
      });
      items.sort(
        (a, b) =>
          (RANK[b.severity] ?? 0) - (RANK[a.severity] ?? 0) ||
          a.oldest_created_at.localeCompare(b.oldest_created_at) ||
          a.customer_no.localeCompare(b.customer_no),
      );
      const offset = Number(params.get('offset') ?? 0);
      const limit = Number(params.get('limit') ?? 50);
      return HttpResponse.json({
        summary: {
          alerts: filtered.length,
          customers: items.length,
          high_alerts: filtered.filter((alert) => alert.severity === 'high').length,
          high_customers: items.filter((item) => item.severity === 'high').length,
          returned_customers: items.filter((item) => item.returned_by).length,
        },
        total: items.length,
        items: items.slice(offset, offset + limit),
      });
    }),
    http.get(`${API}/alerts`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      alertRequests.push(params);
      const filtered = dataset
        .filter((alert) => !params.get('status') || alert.status === params.get('status'))
        .filter((alert) => !params.get('severity') || alert.severity === params.get('severity'))
        .filter((alert) => !params.get('rule_code') || alert.rule_code === params.get('rule_code'))
        .filter((alert) => !params.get('customer_no') || alert.customer_no === params.get('customer_no'))
        .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.alert_id - a.alert_id);
      const offset = Number(params.get('offset') ?? 0);
      const limit = Number(params.get('limit') ?? 50);
      return HttpResponse.json({ total: filtered.length, items: filtered.slice(offset, offset + limit) });
    }),
    http.get(`${API}/dashboard/my-summary`, () =>
      HttpResponse.json({
        decided_today: 4,
        escalated_today: 2,
        returned_to_me: Object.keys(returned).length,
        returned_cases: Object.entries(returned).map(([customerNo, by]) => ({
          customer_no: customerNo,
          customer_name: dataset.find((alert) => alert.customer_no === customerNo)?.customer_name ?? customerNo,
          rule_codes: ['R01'],
          alert_ids: [1],
          returned_by: by,
          returned_at: daysAgo(0),
          note: 'Eksik belge',
        })),
      }),
    ),
  ];
}

export const maskedTransaction: MaskedTransaction = {
  view: 'masked',
  transaction_id: 91,
  tx_time: '2026-10-26T14:12:00',
  direction: 'out',
  amount: '45000.00',
  currency: 'TRY',
  channel: 'internet',
  country_code: 'TR',
  counterparty: 'Kaya T. L. Ş.',
  counterparty_account: '…0311',
  in_alert: true,
};

export function historyEvent(partial: Partial<AlertHistoryEvent> & Pick<AlertHistoryEvent, 'new_status'>): AlertHistoryEvent {
  return {
    old_status: null,
    note: null,
    changed_at: daysAgo(4),
    changed_by: 1,
    actor_name: 'ayse.karaca',
    actor_role: 'analyst',
    ...partial,
  };
}

export function alertDetail(summary: AlertSummary, extra: Partial<AlertDetail> = {}): AlertDetail {
  return {
    ...summary,
    customer: { customer_no: summary.customer_no, customer_name: summary.customer_name, customer_type: 'BIREYSEL' },
    transactions: [maskedTransaction],
    history: [],
    escalated_by: null,
    explanation: null,
    events: [],
    ...extra,
  };
}

export const customerContext: CustomerContext = {
  alert_id: 5518,
  period_start: '2026-05-04T10:00:00',
  profile: {
    customer_type: 'BIREYSEL',
    occupation: 'Öğretmen',
    monthly_income: '28000.00',
    risk_level: 'medium',
    customer_since: 2019,
  },
  accounts: [{ account: '…4410', currency: 'TRY', type: 'current' }],
  summary: [{ currency: 'TRY', incoming_30d: '112000.00', outgoing_30d: '121850.00', avg_monthly_outgoing_6m: '31400.00' }],
  transactions: [{ ...maskedTransaction, counterparty: 'Ö. Kılıç', counterparty_account: '…7781' }],
  truncated: false,
};

/** A full transaction row (GET /transactions, compliance view). */
export const sampleTransaction: Transaction = {
  transaction_id: 91,
  transaction_no: 'TX-0091',
  amount: '45000.00',
  currency: 'TRY',
  tx_time: '2026-10-26T14:12:00',
  country_code: 'TR',
  channel: 'internet',
  sender_account_no: 'TR-ACC-1042',
  sender_customer_no: 'C-1042',
  sender_customer_name: 'Ahmet Yılmaz',
  receiver_account_no: 'TR-ACC-0311',
  receiver_customer_no: 'C-0311',
  receiver_customer_name: 'Kaya Tekstil Ltd. Şti.',
};
