import { http, HttpResponse } from 'msw';
import type { AlertDetail, AlertSummary } from '@/api/schemas/alerts';
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
];

/** Records each GET /alerts query so tests can assert what the UI asked for. */
export const alertRequests: URLSearchParams[] = [];

/**
 * A GET /alerts mock that applies the same filters and paging the API does
 * (status, severity, rule_code, customer_no, offset, limit; newest first).
 */
export function alertsHandler(dataset: AlertSummary[] = queueAlerts) {
  return http.get(`${API}/alerts`, ({ request }) => {
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
  });
}

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

export function alertDetail(summary: AlertSummary, extra: Partial<AlertDetail> = {}): AlertDetail {
  return {
    ...summary,
    transactions: [sampleTransaction],
    history: [{ old_status: null, new_status: 'new', note: null, changed_at: summary.created_at }],
    ...extra,
  };
}
