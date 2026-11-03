import { Download, FileSpreadsheet, Upload, X } from 'lucide-react';
import { useRef, useState, type DragEvent, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/api/client';
import { MAX_UPLOAD_BYTES, MAX_UPLOAD_ROWS, UPLOAD_ENTITIES, type UploadEntity } from '@/api/schemas/uploads';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { StatCard } from '@/components/ui/StatCard';
import { cn } from '@/utils/cn';
import { downloadText } from '@/utils/csv';
import { formatDateTime, formatNumber } from '@/utils/format';
import { CSV_TEMPLATES, checkCsvFile, templateColumns, useUploadCsv, useUploadReport } from './api';
import { UploadErrors } from './UploadErrors';

const MAX_MB = MAX_UPLOAD_BYTES / (1024 * 1024);

function fileSize(bytes: number, language: string): string {
  return bytes >= 1024 * 1024
    ? `${formatNumber(bytes / (1024 * 1024), language, { maximumFractionDigits: 1 })} MB`
    : `${formatNumber(Math.max(1, Math.round(bytes / 1024)), language)} KB`;
}

export default function DataManagementPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [lastBatchId, setLastBatchId] = useState<number | null>(null);

  return (
    <>
      <PageHeader breadcrumb={t('data.breadcrumb')} title={t('nav.dataManagement')} description={t('data.description')} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        {can('upload:create') ? (
          <div className="xl:col-span-3">
            <UploadCard onUploaded={setLastBatchId} />
          </div>
        ) : (
          can('upload:view') && <InlineAlert tone="info" className="xl:col-span-5">{t('data.viewOnly')}</InlineAlert>
        )}
        {can('upload:view') && (
          <div className={can('upload:create') ? 'xl:col-span-2' : 'xl:col-span-3'}>
            <ReportCard defaultBatchId={lastBatchId} />
          </div>
        )}
        {!can('upload:create') && !can('upload:view') && <InlineAlert tone="info">{t('data.noPermission')}</InlineAlert>}
      </div>
    </>
  );
}

function UploadCard({ onUploaded }: { onUploaded: (batchId: number) => void }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [entity, setEntity] = useState<UploadEntity>('customer');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadCsv();

  const pick = (candidate: File | undefined) => {
    upload.reset();
    if (!candidate) return;
    const problem = checkCsvFile(candidate);
    setFileError(problem ? t(`data.${problem}`, { mb: MAX_MB }) : null);
    setFile(problem ? null : candidate);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files[0]);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    upload.mutate({ entity, file }, { onSuccess: (result) => onUploaded(result.batch_id) });
  };

  const result = upload.data;
  return (
    <Card>
      <CardHeader title={t('data.uploadTitle')} description={t('data.orderNote')} />
      <form onSubmit={submit} className="space-y-4 p-5" noValidate>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-48 flex-1">
            <Field label={t('data.entity')}>
              <Select
                value={entity}
                onChange={(event) => {
                  setEntity(event.target.value as UploadEntity);
                  upload.reset();
                }}
              >
                {UPLOAD_ENTITIES.map((value) => (
                  <option key={value} value={value}>
                    {t(`data.entities.${value}`)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Button type="button" onClick={() => downloadText(`${entity}_template.csv`, CSV_TEMPLATES[entity], 'text/csv;charset=utf-8', false)}>
            <Download className="size-4" aria-hidden />
            {t('data.downloadTemplate')}
          </Button>
        </div>
        <p className="text-xs text-muted">
          {t('data.templateColumns')}: <span className="font-mono">{templateColumns(entity).join(', ')}</span>
        </p>

        <div>
          <p className="mb-1.5 text-[13px] font-medium">{t('data.file')}</p>
          {file ? (
            <div className="flex items-center gap-3 rounded-md border border-border-strong px-3 py-3">
              <FileSpreadsheet className="size-5 text-success" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-[13px]">
                {t('data.selected', { name: file.name, size: fileSize(file.size, language) })}
              </span>
              <Button
                size="sm"
                variant="ghost"
                aria-label={t('data.removeFile')}
                onClick={() => {
                  setFile(null);
                  upload.reset();
                  if (inputRef.current) inputRef.current.value = '';
                }}
              >
                <X className="size-4" aria-hidden />
              </Button>
            </div>
          ) : (
            <label
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                'flex cursor-pointer flex-col items-center gap-1 rounded-md border-2 border-dashed px-4 py-8 text-center transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-focus',
                dragging ? 'border-accent bg-accent-soft' : 'border-border-strong hover:bg-surface-hover',
              )}
            >
              <Upload className="mb-1 size-6 text-muted" aria-hidden />
              <span className="text-[13px] font-semibold">{t('data.dropHint')}</span>
              <span className="text-xs text-muted">{t('data.dropLimits', { mb: MAX_MB, rows: MAX_UPLOAD_ROWS })}</span>
              <input
                ref={inputRef}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                aria-label={t('data.file')}
                onChange={(event) => pick(event.target.files?.[0])}
              />
            </label>
          )}
          {fileError && (
            <p className="mt-1.5 text-xs font-medium text-danger" role="alert">
              {fileError}
            </p>
          )}
        </div>

        {entity === 'transaction' && <InlineAlert tone="info">{t('data.transactionNote')}</InlineAlert>}

        <Button type="submit" variant="primary" disabled={!file} loading={upload.isPending}>
          {upload.isPending ? t('data.uploading') : t('data.upload')}
        </Button>

        {upload.isError && <ErrorState error={upload.error} title={t('errors.validation')} />}
        {result && (
          <div className="space-y-4 border-t border-border pt-4" aria-live="polite">
            <InlineAlert tone={result.rejected_rows > 0 ? 'warning' : 'success'} title={t('data.resultTitle', { id: result.batch_id })}>
              {t('data.resultSummary', { accepted: result.accepted_rows, rejected: result.rejected_rows, total: result.total_rows })}
            </InlineAlert>
            <UploadErrors errors={result.errors} batchId={result.batch_id} />
          </div>
        )}
      </form>
    </Card>
  );
}

function ReportCard({ defaultBatchId }: { defaultBatchId: number | null }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  // null = untouched (follow the latest upload); '' = deliberately cleared.
  const [draft, setDraft] = useState<string | null>(null);
  const [requested, setRequested] = useState<number | null>(null);
  const [invalid, setInvalid] = useState(false);
  const report = useUploadReport(requested);
  const value = draft ?? (defaultBatchId ? String(defaultBatchId) : '');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const id = Number(value);
    const ok = Number.isInteger(id) && id > 0;
    setInvalid(!ok);
    if (ok) setRequested(id);
  };

  const notFound = report.error instanceof ApiError && report.error.kind === 'notFound';
  return (
    <Card>
      <CardHeader title={t('data.reportTitle')} description={t('data.reportDescription')} />
      <div className="space-y-4 p-5">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3" noValidate>
          <div className="w-44">
            <Field label={t('data.batchId')} error={invalid ? t('data.batchIdInvalid') : undefined}>
              <Input type="number" min={1} step={1} inputMode="numeric" value={value} onChange={(event) => setDraft(event.target.value)} />
            </Field>
          </div>
          <Button type="submit" loading={report.isFetching}>
            {t('data.loadReport')}
          </Button>
        </form>

        {notFound ? (
          <InlineAlert tone="warning">{t('data.reportNotFound')}</InlineAlert>
        ) : report.isError ? (
          <ErrorState error={report.error} onRetry={() => void report.refetch()} />
        ) : report.data ? (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-3 text-[13px]">
              <div>
                <dt className="text-xs text-muted">{t('data.reportFile')}</dt>
                <dd className="font-mono break-all">{report.data.file_name ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">{t('data.reportUploaded')}</dt>
                <dd>{formatDateTime(report.data.uploaded_at, language)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">{t('data.entity')}</dt>
                <dd>
                  {(UPLOAD_ENTITIES as readonly string[]).includes(report.data.entity_type)
                    ? t(`data.entities.${report.data.entity_type as UploadEntity}`)
                    : report.data.entity_type}
                </dd>
              </div>
            </dl>
            <div className="grid grid-cols-3 gap-2">
              <StatCard label={t('data.accepted')} value={formatNumber(report.data.accepted_rows, language)} />
              <StatCard
                label={t('data.rejected')}
                value={formatNumber(report.data.rejected_rows, language)}
                tone={report.data.rejected_rows > 0 ? 'danger' : 'default'}
              />
              <StatCard label={t('data.totalRows')} value={formatNumber(report.data.total_rows, language)} />
            </div>
            <UploadErrors errors={report.data.errors} batchId={report.data.batch_id} />
          </div>
        ) : null}
      </div>
    </Card>
  );
}
