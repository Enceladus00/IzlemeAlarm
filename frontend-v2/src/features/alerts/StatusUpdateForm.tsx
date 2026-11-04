import { ShieldAlert } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ApiError } from '@/api/client';
import { MAX_DECISION_ALERTS, NOTE_MAX_LENGTH, type AlertDetail, type AlertStatus } from '@/api/schemas/alerts';
import { useAuth } from '@/auth/auth-context';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Textarea } from '@/components/ui/Select';
import { useServerMessage } from '@/utils/errors';
import { formatDateTime } from '@/utils/format';
import { useAlertDecision, useCustomerAlerts } from './api';
import { FOUR_EYES_TARGETS, availableTransitions } from './workflow';

type FormError = 'decisionRequired' | 'noteRequired' | 'noteTooLong' | 'alertsRequired' | 'tooManyAlerts';

/**
 * Decision form (API design 7.3). One decision is applied atomically to the
 * selected alerts of the same customer in the same status (POST /alerts/decisions).
 */
export function StatusUpdateForm({ alert, backSearch }: { alert: AlertDetail; backSearch: string }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { permissions, profile } = useAuth();
  const navigate = useNavigate();
  const mutation = useAlertDecision();
  const serverMessage = useServerMessage();
  const siblings = useCustomerAlerts(alert.customer_no, alert.status as AlertStatus);

  const transitions = availableTransitions(alert.status, permissions);
  const escalatedByMe =
    alert.status === 'in_review' && !!profile && alert.escalated_by?.actor_name === profile.username;

  const [target, setTarget] = useState<AlertStatus | null>(null);
  const [note, setNote] = useState('');
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set([alert.alert_id]));
  const [formError, setFormError] = useState<FormError | null>(null);

  // A different alert (or fresh sibling data) resets the form; all same-status alerts start selected.
  const candidates = siblings.data?.items ?? [];
  const candidateKey = candidates.map((item) => item.alert_id).join(',');
  useEffect(() => {
    setTarget(null);
    setNote('');
    setFormError(null);
    setSelected(new Set(candidates.length ? candidates.map((item) => item.alert_id) : [alert.alert_id]));
    mutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alert.alert_id, alert.status, candidateKey]);

  if (transitions.length === 0) {
    return <InlineAlert tone="info">{t('alertDetail.readOnly')}</InlineAlert>;
  }

  const toggle = (alertId: number) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(alertId)) next.delete(alertId);
      else next.add(alertId);
      return next;
    });

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = note.trim();
    const error: FormError | null = !target
      ? 'decisionRequired'
      : selected.size === 0
        ? 'alertsRequired'
        : selected.size > MAX_DECISION_ALERTS
          ? 'tooManyAlerts'
          : !trimmed
            ? 'noteRequired'
            : trimmed.length > NOTE_MAX_LENGTH
              ? 'noteTooLong'
              : null;
    setFormError(error);
    if (error || !target) return;
    const transition = transitions.find((item) => item.to === target)!;
    mutation.mutate(
      { alert_ids: [...selected].sort((a, b) => a - b), status: target, note: trimmed },
      {
        onSuccess: () =>
          navigate(`/alerts${backSearch}`, {
            state: { flash: t(`alertDetail.decided.${transition.success}`, { count: selected.size }) },
          }),
      },
    );
  };

  const failure = mutation.error;
  const failureText =
    failure instanceof ApiError && failure.alertId !== null
      ? t('alertDetail.decisionFailed', { id: failure.alertId, reason: serverMessage(failure) })
      : failure
        ? serverMessage(failure)
        : null;

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {alert.status === 'in_review' && alert.escalated_by && (
        <p className="flex items-center gap-1.5 text-[13px]">
          <ShieldAlert className="size-4 text-warning" aria-hidden />
          {t('alertDetail.escalatedBy', {
            name: alert.escalated_by.actor_name ?? '—',
            at: formatDateTime(alert.escalated_by.changed_at, language),
          })}
        </p>
      )}
      {escalatedByMe && <InlineAlert tone="warning">{t('alertDetail.fourEyes')}</InlineAlert>}

      <fieldset className="space-y-2">
        <legend className="mb-1 text-[13px] font-medium">
          {t('alertDetail.newStatus')} <span className="text-danger">*</span>
        </legend>
        {transitions.map((transition) => {
          const locked = escalatedByMe && FOUR_EYES_TARGETS.includes(transition.to);
          return (
            <label key={transition.to} className="flex items-center gap-2 text-[13px]">
              <input
                type="radio"
                name="decision"
                value={transition.to}
                checked={target === transition.to}
                disabled={locked}
                onChange={() => setTarget(transition.to)}
              />
              <span className={locked ? 'text-subtle line-through' : undefined}>
                {t(`alertDetail.decisions.${transition.label}`)}
              </span>
            </label>
          );
        })}
      </fieldset>

      <fieldset className="space-y-1.5">
        <legend className="mb-1 text-[13px] font-medium">
          {t('alertDetail.applyTo')} <span className="text-danger">*</span>
        </legend>
        {(candidates.length ? candidates : [alert]).map((item) => (
          <label key={item.alert_id} className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={selected.has(item.alert_id)} onChange={() => toggle(item.alert_id)} />
            <span className="font-mono">#{item.alert_id}</span>
            <span className="font-semibold">{item.rule_code}</span>
            <span className="truncate text-muted">{item.rule_name}</span>
          </label>
        ))}
      </fieldset>

      <Field
        label={
          <>
            {t('alertDetail.note')}
            <span className="text-danger"> *</span>
          </>
        }
        hint={t('alertDetail.noteCounter', { count: note.length, max: NOTE_MAX_LENGTH })}
        error={
          formError === 'noteRequired'
            ? t('alertDetail.noteRequired')
            : formError === 'noteTooLong'
              ? t('alertDetail.noteTooLong', { max: NOTE_MAX_LENGTH })
              : undefined
        }
      >
        <Textarea
          rows={4}
          maxLength={NOTE_MAX_LENGTH}
          placeholder={t('alertDetail.notePlaceholder')}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </Field>

      {formError && formError !== 'noteRequired' && formError !== 'noteTooLong' && (
        <InlineAlert tone="warning" live>
          {t(`alertDetail.formErrors.${formError}`, { max: MAX_DECISION_ALERTS })}
        </InlineAlert>
      )}
      {failureText && (
        <InlineAlert tone="danger" title={t('alertDetail.decisionNotSaved')} live>
          {failureText}
        </InlineAlert>
      )}

      <Button type="submit" variant="primary" loading={mutation.isPending}>
        {t('alertDetail.save')}
      </Button>
    </form>
  );
}
