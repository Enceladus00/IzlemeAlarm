import { z } from 'zod';
import { apiDateTime, decimal, pageSchema } from './common';

/** backend/services/transaction_service.py::transaction_view */
export const transactionSchema = z.object({
  transaction_id: z.number(),
  transaction_no: z.string(),
  amount: decimal,
  currency: z.string(),
  tx_time: apiDateTime,
  country_code: z.string(),
  channel: z.string(),
  sender_account_no: z.string(),
  sender_customer_no: z.string(),
  sender_customer_name: z.string(),
  receiver_account_no: z.string(),
  receiver_customer_no: z.string(),
  receiver_customer_name: z.string(),
  /** Only present on GET /transactions. */
  alert_linked: z.boolean().optional(),
});
export type Transaction = z.infer<typeof transactionSchema>;

/** GET /transactions */
export const transactionPageSchema = pageSchema(transactionSchema);
export type TransactionPage = z.infer<typeof transactionPageSchema>;

/** GET /transactions/summary (K12): totals over every matching transfer, computed by the API. */
export const transactionSummarySchema = z.object({
  transfer_count: z.number(),
  account_count: z.number(),
  by_currency: z.array(
    z.object({
      currency: z.string(),
      total: decimal,
      incoming: decimal.nullable(),
      outgoing: decimal.nullable(),
      count: z.number(),
      incoming_count: z.number().nullable(),
      outgoing_count: z.number().nullable(),
    }),
  ),
  timeline: z.object({
    granularity: z.enum(['day', 'week']),
    points: z.array(z.object({ date: z.string(), count: z.number() })),
  }),
  /** Account labels are masked by the API ("TR…4410"); no names are sent. */
  routes: z.array(
    z.object({
      sender_account: z.string(),
      receiver_account: z.string(),
      sender_is_focus: z.boolean(),
      receiver_is_focus: z.boolean(),
      currency: z.string(),
      count: z.number(),
      amount: decimal,
      alert_linked: z.number(),
      /** Signed handles to expand a counterparty (GET /transactions/summary?account_ref=). */
      sender_ref: z.string().default(''),
      receiver_ref: z.string().default(''),
      /** Masked owner names ("K. Kara", "Nehir L. A."). */
      sender_label: z.string().default(''),
      receiver_label: z.string().default(''),
      /** Codes of the rules whose alerts include transfers on this route. */
      alert_rules: z.array(z.string()).default([]),
    }),
  ),
  other_routes: z.object({
    route_count: z.number(),
    count: z.number(),
    by_currency: z.array(z.object({ currency: z.string(), amount: decimal })).default([]),
  }),
  /** Money into / out of the focus per time bucket and currency; empty without a focus. */
  flow_timeline: z
    .array(z.object({ date: z.string(), currency: z.string(), incoming: decimal, outgoing: decimal }))
    .default([]),
});
export type TransactionSummary = z.infer<typeof transactionSummarySchema>;
