import { z } from 'zod';
import { apiDateTime } from './common';

export const UPLOAD_ENTITIES = ['customer', 'account', 'transaction'] as const;
export type UploadEntity = (typeof UPLOAD_ENTITIES)[number];

/** Limits enforced by backend/services/upload_service.py. */
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
export const MAX_UPLOAD_ROWS = 5000;

export const uploadRowErrorSchema = z.object({
  row_number: z.number(),
  reason: z.string(),
  row_data: z.record(z.string(), z.unknown()).nullable(),
});
export type UploadRowError = z.infer<typeof uploadRowErrorSchema>;

/** POST /uploads */
export const uploadResultSchema = z.object({
  batch_id: z.number(),
  entity_type: z.string(),
  total_rows: z.number(),
  accepted_rows: z.number(),
  rejected_rows: z.number(),
  errors: z.array(uploadRowErrorSchema),
});
export type UploadResult = z.infer<typeof uploadResultSchema>;

/** GET /uploads/{batch_id} */
export const uploadReportSchema = uploadResultSchema.extend({
  file_name: z.string().nullable(),
  uploaded_at: apiDateTime.nullable(),
});
export type UploadReport = z.infer<typeof uploadReportSchema>;
