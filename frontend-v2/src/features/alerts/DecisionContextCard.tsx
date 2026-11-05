import { useTranslation } from 'react-i18next';
import type { AlertDetail } from '@/api/schemas/alerts';
import { Card } from '@/components/ui/Card';
import { cn } from '@/utils/cn';
import { formatDateTime } from '@/utils/format';
import { decisionContext } from './workflow';

/**
 * E05 / E11: shows first why the alert is where it is — the analyst's reason for
 * escalating, compliance's reason for returning it, or the final decision.
 */
export function DecisionContextCard({ alert }: { alert: AlertDetail }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const context = decisionContext(alert);
  if (!context) return null;
  const { kind, event } = context;
  const role = event.actor_role
    ? t(`roles.${event.actor_role as 'analyst'}`, { defaultValue: event.actor_role })
    : null;

  return (
    <Card className={cn('border-l-4', kind === 'escalated' ? 'border-l-warning' : kind === 'returned' ? 'border-l-info' : 'border-l-border')}>
      <div className="space-y-2 p-5">
        <h2 className="text-[15px] font-semibold">{t(`decisionContext.${kind}Title`)}</h2>
        <p className="text-[13px] text-muted">
          <span className="font-semibold text-fg">{event.actor_name ?? '—'}</span>
          {role && <> · {role}</>} · {formatDateTime(event.changed_at, language)}
          {kind === 'decided' && <> · {t(`alertStatus.${alert.status as 'closed'}`)}</>}
        </p>
        <blockquote className="border-l-2 border-border bg-neutral-soft px-3 py-2 text-[13px] whitespace-pre-line">
          {event.note?.trim() ? event.note : <span className="text-muted">{t('decisionContext.noNote')}</span>}
        </blockquote>
      </div>
    </Card>
  );
}
