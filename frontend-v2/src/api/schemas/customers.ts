import { z } from 'zod';
import { apiDateTime, decimal, pageSchema } from './common';

/* Mirrors backend/api/responses.py (customers and accounts, customer:view). */

export const CUSTOMER_TYPE_VALUES = ['BIREYSEL', 'KURUMSAL'] as const;
export const RISK_LEVELS = ['low', 'medium', 'high'] as const;

/** GET /customers item: name, number and counts only (not view-logged). */
export const customerListItemSchema = z.object({
  customer_no: z.string(),
  full_name: z.string(),
  customer_type: z.string().nullable(),
  risk_level: z.string().nullable(),
  is_active: z.boolean(),
  account_count: z.number(),
  open_alert_count: z.number(),
});
export type CustomerListItem = z.infer<typeof customerListItemSchema>;
export const customerPageSchema = pageSchema(customerListItemSchema);

/** GET /customers/{no}: full profile; every call is written to the audit log (K6). */
export const customerProfileSchema = z.object({
  customer_no: z.string(),
  full_name: z.string(),
  customer_type: z.string().nullable(),
  occupation: z.string().nullable(),
  monthly_income: decimal.nullable(),
  risk_level: z.string().nullable(),
  is_active: z.boolean(),
  created_at: apiDateTime.nullable(),
  accounts: z.array(
    z.object({
      account_no: z.string(),
      currency: z.string(),
      account_type: z.string().nullable(),
      is_active: z.boolean(),
      opened_at: z.string().nullable(),
      transaction_count: z.number(),
    }),
  ),
  alerts: z.object({ open: z.number(), total: z.number(), by_status: z.record(z.string(), z.number()) }),
});
export type CustomerProfile = z.infer<typeof customerProfileSchema>;

const counterpartySchema = z.object({
  account_no: z.string(),
  customer_no: z.string(),
  customer_name: z.string(),
  currency: z.string(),
  count: z.number(),
  amount: decimal,
  /** E12 "YENİ": no transaction with the customer in the 12 months before the period. */
  is_new: z.boolean(),
});
export type Counterparty = z.infer<typeof counterpartySchema>;

/** GET /customers/{no}/analysis?days=30|90|180 (E12); logged as a customer view. */
export const customerAnalysisSchema = z.object({
  customer_no: z.string(),
  days: z.number(),
  date_from: z.string(),
  date_to: z.string(),
  monthly: z.array(z.object({ month: z.string(), currency: z.string(), incoming: decimal, outgoing: decimal })),
  income_check: z.object({
    monthly_income: decimal.nullable(),
    currency: z.string(),
    peak_month: z.string().nullable(),
    peak_direction: z.enum(['incoming', 'outgoing']).nullable(),
    peak_amount: decimal.nullable(),
    ratio: decimal.nullable(),
    threshold: decimal,
    exceeded: z.boolean(),
  }),
  counterparties: z.object({ incoming: z.array(counterpartySchema), outgoing: z.array(counterpartySchema) }),
});
export type CustomerAnalysis = z.infer<typeof customerAnalysisSchema>;

/** GET /accounts item: full account numbers, so each page is view-logged (K6). */
export const accountListItemSchema = z.object({
  account_no: z.string(),
  customer_no: z.string(),
  customer_name: z.string(),
  currency: z.string(),
  account_type: z.string().nullable(),
  is_active: z.boolean(),
  opened_at: z.string().nullable(),
});
export type AccountListItem = z.infer<typeof accountListItemSchema>;
export const accountPageSchema = pageSchema(accountListItemSchema);
