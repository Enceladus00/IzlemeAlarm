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

/** GET /alerts/{id}/customer-transactions and GET /customers/{no}/transactions */
export const customerHistorySchema = z.object({
  customer_no: z.string(),
  customer_name: z.string(),
  items: z.array(transactionSchema),
});
export type CustomerHistory = z.infer<typeof customerHistorySchema>;
