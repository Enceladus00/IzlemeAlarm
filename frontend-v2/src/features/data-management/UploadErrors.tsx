import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { UploadRowError } from '@/api/schemas/uploads';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { downloadText } from '@/utils/csv';
import { formatNumber } from '@/utils/format';
import { rejectionCsv } from './api';

export function UploadErrors({ errors, batchId }: { errors: UploadRowError[]; batchId: number }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  if (errors.length === 0) return <InlineAlert tone="success">{t('data.rejectionsNone')}</InlineAlert>;
  // K13: another user's upload comes without row contents.
  const hidden = errors.every((error) => error.row_data === null);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">
          {t('data.rejectionsTitle')} · {formatNumber(errors.length, language)}
        </h3>
        {!hidden && (
          <Button size="sm" onClick={() => downloadText(`upload-${batchId}-rejections.csv`, rejectionCsv(errors))}>
            <Download className="size-3.5" aria-hidden />
            {t('data.downloadRejections')}
          </Button>
        )}
      </div>
      {hidden && <InlineAlert tone="info">{t('data.rowDataHidden')}</InlineAlert>}
      <DataTable
        label={t('data.rejectionsTitle')}
        rows={errors}
        rowKey={(error) => String(error.row_number)}
        maxHeight={360}
        columns={[
          { key: 'row', header: t('data.rowNumber'), align: 'right', render: (error) => formatNumber(error.row_number, language) },
          { key: 'reason', header: t('data.reason'), render: (error) => <span className="font-medium text-danger">{error.reason}</span> },
          {
            key: 'data',
            header: t('data.rowData'),
            render: (error) => (
              <span className="font-mono text-xs break-all text-muted">
                {error.row_data === null
                  ? '—'
                  : Object.entries(error.row_data)
                      .map(([key, value]) => `${key}=${String(value)}`)
                      .join(' · ')}
              </span>
            ),
          },
        ]}
      />
    </div>
  );
}
