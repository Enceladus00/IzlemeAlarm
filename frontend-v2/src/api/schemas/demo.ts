import { z } from 'zod';
import { apiDateTime, decimal } from './common';

const customerRow = z.object({
  customer_no: z.string(),
  full_name: z.string(),
  customer_type: z.string().nullable(),
  monthly_income: decimal.nullable(),
  account_count: z.number(),
  is_active: z.boolean(),
});

const accountRow = z.object({
  account_no: z.string(),
  customer_no: z.string(),
  currency: z.string(),
  account_type: z.string().nullable(),
  opened_at: z.string().nullable(),
  is_active: z.boolean(),
});

const transactionRow = z.object({
  transaction_no: z.string(),
  sender_customer_no: z.string(),
  sender_account_no: z.string(),
  receiver_customer_no: z.string(),
  receiver_account_no: z.string(),
  amount: decimal,
  currency: z.string(),
  tx_time: apiDateTime,
  channel: z.string(),
  is_active: z.boolean(),
});

/** A designed scenario; result fields are present only after a seed run. */
export const demoScenarioSchema = z.object({
  rule_code: z.string(),
  customer_no: z.string(),
  account_no: z.string(),
  intent: z.string(),
  expected_signal: z.string(),
  result_status: z.string().optional(),
  parameter_status: z.string().nullable().optional(),
  score: decimal.nullable().optional(),
  evidence_transactions: z.number().optional(),
  evidence_transaction_numbers: z.array(z.string()).optional(),
  observed_signal: z.boolean().nullable().optional(),
  passed: z.boolean().nullable().optional(),
});
export type DemoScenario = z.infer<typeof demoScenarioSchema>;

/** GET /demo/status */
export const demoStatusSchema = z.object({
  seeded: z.boolean(),
  fixture_ready: z.boolean(),
  customers: z.number(),
  accounts: z.number(),
  transactions: z.number(),
  customer_rows: z.array(customerRow),
  account_rows: z.array(accountRow),
  transaction_rows: z.array(transactionRow),
  scenarios: z.array(demoScenarioSchema),
  seed_enabled: z.boolean().optional(),
});
export type DemoStatus = z.infer<typeof demoStatusSchema>;

/** Per-rule execution summary from the detection engine (extra keys kept). */
const ruleSummarySchema = z
  .object({
    evaluated: z.number(),
    alerts: z.number(),
    skipped_unset: z.record(z.string(), z.number()),
    elapsed_ms: z.number().optional(),
  })
  .passthrough();

/** POST /demo/seed */
export const demoRunSchema = demoStatusSchema.extend({
  run_id: z.string(),
  created_alerts: z.number(),
  parameter_mode: z.string(),
  saved_rule_settings_used: z.boolean().optional(),
  rule_summary: z.record(z.string(), ruleSummarySchema),
});
export type DemoRun = z.infer<typeof demoRunSchema>;
