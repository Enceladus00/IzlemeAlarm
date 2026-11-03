import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import {
  ALERT_STATUSES,
  NOTE_MAX_LENGTH,
  NOTE_REQUIRED_STATUSES,
  type AlertStatus,
} from '@/api/schemas/alerts';
import { Button } from '@/components/ui/Button';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Select, Textarea } from '@/components/ui/Select';
import { useUpdateAlertStatus } from './api';

/** Mirrors the server rules: closing/confirming needs a note; max 2000 characters. */
const formSchema = z
  .object({
    status: z.enum(ALERT_STATUSES),
    note: z.string().max(NOTE_MAX_LENGTH, 'alertDetail.noteTooLong'),
  })
  .refine((value) => !NOTE_REQUIRED_STATUSES.includes(value.status) || value.note.trim().length > 0, {
    path: ['note'],
    message: 'alertDetail.noteRequired',
  });
type FormValues = z.infer<typeof formSchema>;

function asStatus(value: string): AlertStatus {
  return (ALERT_STATUSES as readonly string[]).includes(value) ? (value as AlertStatus) : 'new';
}

export function StatusUpdateForm({ alertId, currentStatus }: { alertId: number; currentStatus: string }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const mutation = useUpdateAlertStatus(alertId);
  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { status: asStatus(currentStatus), note: '' },
  });

  // Switching to another alert resets the form to that alert's status.
  useEffect(() => {
    reset({ status: asStatus(currentStatus), note: '' });
    mutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertId]);

  const status = watch('status');
  const note = watch('note');
  const noteRequired = NOTE_REQUIRED_STATUSES.includes(status);

  const onSubmit = handleSubmit((values) => {
    const trimmed = values.note.trim();
    mutation.mutate(
      { status: values.status, note: trimmed || null },
      { onSuccess: () => reset({ status: values.status, note: '' }) },
    );
  });

  const result = mutation.data;
  const noteError = errors.note?.message;

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <Field label={t('alertDetail.newStatus')}>
        <Select {...register('status')}>
          {ALERT_STATUSES.map((value) => (
            <option key={value} value={value}>
              {t(`alertStatus.${value}`)}
            </option>
          ))}
        </Select>
      </Field>
      <Field
        label={
          <>
            {t('alertDetail.note')}
            {noteRequired && <span className="text-danger"> *</span>}
          </>
        }
        hint={t('alertDetail.noteCounter', { count: note.length, max: NOTE_MAX_LENGTH })}
        error={
          noteError &&
          (noteError === 'alertDetail.noteTooLong'
            ? t('alertDetail.noteTooLong', { max: NOTE_MAX_LENGTH })
            : t('alertDetail.noteRequired'))
        }
      >
        <Textarea rows={4} placeholder={t('alertDetail.notePlaceholder')} {...register('note')} />
      </Field>

      {mutation.isError && <ErrorState error={mutation.error} title={t('errors.validation')} />}
      {result && (
        <InlineAlert tone={result.changed ? 'success' : 'info'} live>
          {result.changed
            ? t('alertDetail.saved')
            : mutation.variables?.note
              ? t('alertDetail.savedNoteOnly')
              : t('alertDetail.noChange')}
        </InlineAlert>
      )}

      <Button type="submit" variant="primary" loading={mutation.isPending} lang={language}>
        {t('alertDetail.save')}
      </Button>
    </form>
  );
}
