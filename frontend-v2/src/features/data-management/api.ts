import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@/api/client';
import {
  MAX_UPLOAD_BYTES,
  uploadHistorySchema,
  uploadReportSchema,
  uploadResultSchema,
  type UploadEntity,
  type UploadRowError,
} from '@/api/schemas/uploads';
import { toCsv } from '@/utils/csv';

/** Same templates as frontend/app_pages/data_upload.py. */
export const CSV_TEMPLATES: Record<UploadEntity, string> = {
  customer:
    'customer_no,full_name,customer_type,occupation,monthly_income,risk_level\n' +
    'DEMO-NEW-001,Example Customer,person,Engineer,50000,low\n',
  account: 'account_no,customer_no,currency,account_type,opened_at\n' + 'DEMO-NEW-ACC-001,DEMO-001,TRY,current,2026-01-01\n',
  transaction:
    'transaction_no,sender_account_no,receiver_account_no,amount,currency,tx_time,channel,country_code\n' +
    'NEW-TX-001,DEMO-ACC-001,DEMO-ACC-002,1250,TRY,2026-01-01T10:00:00,mobile,US\n',
};

export function templateColumns(entity: UploadEntity): string[] {
  return CSV_TEMPLATES[entity].split('\n')[0]!.split(',');
}

/** POST /uploads?entity= (multipart) — requires upload:create. */
export function useUploadCsv() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entity, file }: { entity: UploadEntity; file: File }) => {
      const formData = new FormData();
      formData.append('file', file, file.name);
      return apiRequest('/uploads', { method: 'POST', query: { entity }, formData, schema: uploadResultSchema });
    },
    onSuccess: (result, { entity }) => {
      // New records change every overview; transaction uploads also create alerts.
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      void queryClient.invalidateQueries({ queryKey: ['admin'] });
      void queryClient.invalidateQueries({ queryKey: ['demo'] });
      void queryClient.invalidateQueries({ queryKey: ['uploads', result.batch_id] });
      void queryClient.invalidateQueries({ queryKey: ['uploads', 'list'] });
      if (entity === 'transaction') {
        void queryClient.invalidateQueries({ queryKey: ['alerts'] });
        void queryClient.invalidateQueries({ queryKey: ['transactions'] });
      }
    },
  });
}

/** GET /uploads/{id} — requires upload:view. */
export function useUploadReport(batchId: number | null) {
  return useQuery({
    queryKey: ['uploads', batchId],
    queryFn: ({ signal }) => apiRequest(`/uploads/${batchId}`, { schema: uploadReportSchema, signal }),
    enabled: batchId !== null,
  });
}

/** GET /uploads — the latest uploads, newest first (upload:view). */
export function useUploadHistory(enabled: boolean) {
  return useQuery({
    queryKey: ['uploads', 'list'],
    queryFn: ({ signal }) => apiRequest('/uploads', { query: { limit: 20 }, schema: uploadHistorySchema, signal }),
    enabled,
  });
}

/** Same pre-checks the API makes, so obvious mistakes fail before uploading. */
export function checkCsvFile(file: File): 'errorNotCsv' | 'errorTooLarge' | 'errorEmpty' | null {
  if (!file.name.toLowerCase().endsWith('.csv')) return 'errorNotCsv';
  if (file.size > MAX_UPLOAD_BYTES) return 'errorTooLarge';
  if (file.size === 0) return 'errorEmpty';
  return null;
}

/** Rejection report as CSV: row number, reason, then every original column. */
export function rejectionCsv(errors: UploadRowError[]): string {
  const columns = [...new Set(errors.flatMap((error) => Object.keys(error.row_data ?? {})))].sort();
  return toCsv(
    ['row_number', 'reason', ...columns],
    errors.map((error) => [error.row_number, error.reason, ...columns.map((column) => error.row_data?.[column] ?? '')]),
  );
}
