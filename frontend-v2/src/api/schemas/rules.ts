import { z } from 'zod';
import { decimal } from './common';

export const CUSTOMER_TYPES = ['BIREYSEL', 'KURUMSAL'] as const;
export type CustomerType = (typeof CUSTOMER_TYPES)[number];

export const PARAMETER_STATUSES = ['UNSET', 'PROVISIONAL', 'APPROVED'] as const;
export type ParameterStatus = (typeof PARAMETER_STATUSES)[number];

export const ruleParameterSchema = z.object({
  name: z.string(),
  type: z.string(),
  unit: z.string(),
  meaning: z.string(),
  required: z.boolean(),
});
export type RuleParameter = z.infer<typeof ruleParameterSchema>;

export const ruleMetadataSchema = z.object({
  steps: z.array(z.string()),
  alert_mode: z.string(),
  parameters: z.array(ruleParameterSchema),
  analyst_review_notes: z.array(z.string()),
  feasibility: z.string(),
  feasibility_reason: z.string(),
});
export type RuleMetadata = z.infer<typeof ruleMetadataSchema>;

/** GET /rules item (rule_service.py::list_rules). Legacy rules have metadata: null. */
export const ruleSchema = z.object({
  rule_code: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  is_active: z.boolean(),
  weight: decimal.nullable(),
  /** Per customer type for registered rules; a flat legacy object otherwise. */
  thresholds: z.record(z.string(), z.unknown()).nullable(),
  metadata: ruleMetadataSchema.nullable(),
});
export type Rule = z.infer<typeof ruleSchema>;

export const rulesSchema = z.array(ruleSchema);

export interface CustomerTypeThresholds {
  status: ParameterStatus;
  values: Record<string, unknown>;
}

/** PUT /rules/{code} body. */
export interface RuleUpdate {
  is_active: boolean;
  weight: number;
  thresholds: Record<CustomerType, CustomerTypeThresholds>;
}

export const ruleUpdateResultSchema = z.object({
  rule_code: z.string(),
  is_active: z.boolean(),
  weight: decimal.nullable(),
  thresholds: z.record(z.string(), z.unknown()).nullable(),
});
