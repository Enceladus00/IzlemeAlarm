import { CircleCheck, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useAlertDetail } from '@/features/alerts/api';
import { formatDateTime } from '@/utils/format';

const KNOWN_STATUSES = ['new', 'in_review', 'closed', 'confirmed_suspicious'] as const;
type KnownStatus = (typeof KNOWN_STATUSES)[number];

function isKnown(status: string | null): status is KnownStatus {
  return status !== null && (KNOWN_STATUSES as readonly string[]).includes(status);
}

/**
 * E06 "Bu kararın izi": the alert's path from the rule engine through the analyst
 * to the compliance decision, read from the alert's own status history.
 */
export function DecisionTrace({ alertId }: { alertId: number }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const detail = useAlertDetail(alertId);

  if (detail.isPending) return <div className="h-20 animate-pulse rounded bg-neutral-soft" aria-hidden />;
  if (detail.isError) return <p className="text-[13px] text-muted">{t('decisionTrace.unavailable')}</p>;

  const alert = detail.data;
  const changes = [...alert.history]
    .filter((event) => event.old_status !== event.new_status && event.old_status !== null)
    .sort((a, b) => a.changed_at.localeCompare(b.changed_at));
  const status = (value: string | null) =>
    isKnown(value) ? t(`alertStatus.${value}`) : (value ?? '—');

  // Four eyes: the last escalation and the final decision after it were made by different people.
  const lastEscalation = changes.filter((event) => event.new_status === 'in_review').at(-1);
  const decision = changes.at(-1);
  const decided =
    lastEscalation !== undefined &&
    decision !== undefined &&
    decision.old_status === 'in_review' &&
    (decision.new_status === 'closed' || decision.new_status === 'confirmed_suspicious');
  const fourEyesHeld = decided && lastEscalation.changed_by !== decision.changed_by;

  return (
    <section aria-label={t('decisionTrace.title')} className="space-y-3">
      <h3 className="text-[13px] font-semibold">
        {t('decisionTrace.title')} ·{' '}
        <Link to={`/alerts/${alert.alert_id}`} className="font-mono text-info hover:underline">
          #{alert.alert_id}
        </Link>
      </h3>
      <ol className="space-y-2 border-l-2 border-border pl-4 text-[13px]">
        <li>
          <p className="font-semibold">{t('decisionTrace.created', { rule: alert.rule_code })}</p>
          <p className="text-xs text-muted">
            {t('decisionTrace.system')} · {formatDateTime(alert.created_at, language)}
          </p>
        </li>
        {changes.map((event, index) => (
          <li key={`${event.changed_at}-${index}`}>
            <p className="font-semibold">{t('decisionTrace.change', { from: status(event.old_status), to: status(event.new_status) })}</p>
            <p className="text-xs text-muted">
              {event.actor_name ?? '—'}
              {event.actor_role && <> · {t(`roles.${event.actor_role as 'analyst'}`, { defaultValue: event.actor_role })}</>}
              {' · '}
              {formatDateTime(event.changed_at, language)}
            </p>
          </li>
        ))}
      </ol>
      {decided &&
        (fourEyesHeld ? (
          <p className="flex items-center gap-2 rounded-md bg-success-soft px-3 py-2 text-[13px] text-success">
            <CircleCheck className="size-4 shrink-0" aria-hidden />
            {t('decisionTrace.fourEyesHeld')}
          </p>
        ) : (
          <p className="flex items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">
            <TriangleAlert className="size-4 shrink-0" aria-hidden />
            {t('decisionTrace.fourEyesBroken')}
          </p>
        ))}
    </section>
  );
}
