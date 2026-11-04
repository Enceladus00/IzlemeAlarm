import { ChevronRight, Lightbulb } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Explanation } from '@/api/schemas/alerts';
import { Card, CardHeader } from '@/components/ui/Card';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { formatNumber } from '@/utils/format';
import { explanationVariables, fillTemplate } from './explanation';

/** Where the score sits between the threshold (0.5) and the certain point (0.9). */
function ScoreScale({ explanation }: { explanation: Explanation }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const score = Number(explanation.score ?? 0);
  const position = Math.min(100, Math.max(0, score * 100));
  const fmt = (value: string | null) => (value === null ? '—' : formatNumber(value, language, { maximumFractionDigits: 4 }));
  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-2 gap-3 text-[13px] sm:grid-cols-4">
        <div>
          <dt className="text-xs text-muted">{t('explanation.rawValue')}</dt>
          <dd className="font-mono">{fmt(explanation.raw_x)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t('explanation.threshold')}</dt>
          <dd className="font-mono">{fmt(explanation.x_esik)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t('explanation.certain')}</dt>
          <dd className="font-mono">{fmt(explanation.x_kesin)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t('explanation.score')}</dt>
          <dd className="font-mono font-semibold">{fmt(explanation.score)}</dd>
        </div>
      </dl>
      <div
        className="relative h-2 rounded-full bg-gradient-to-r from-neutral-soft via-warning/40 to-danger/60"
        role="img"
        aria-label={t('explanation.scaleLabel', { score: fmt(explanation.score) })}
      >
        <span className="absolute top-0 h-2 w-px bg-fg/50" style={{ left: '50%' }} aria-hidden />
        <span className="absolute top-0 h-2 w-px bg-fg/50" style={{ left: '90%' }} aria-hidden />
        <span
          className="absolute -top-1 size-4 -translate-x-1/2 rounded-full border-2 border-surface bg-fg"
          style={{ left: `${position}%` }}
          aria-hidden
        />
      </div>
      <div className="relative h-4 text-[11px] text-muted" aria-hidden>
        <span className="absolute -translate-x-1/2" style={{ left: '50%' }}>0,5</span>
        <span className="absolute -translate-x-1/2" style={{ left: '90%' }}>0,9</span>
      </div>
    </div>
  );
}

/** K8: "Why was this triggered?" — summary sentence, score position, rule steps. */
export function ExplanationPanel({ explanation }: { explanation: Explanation | null }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [open, setOpen] = useState(false);

  if (!explanation) {
    return (
      <Card>
        <CardHeader title={t('explanation.title')} />
        <div className="p-5">
          <InlineAlert tone="info">{t('explanation.legacy')}</InlineAlert>
        </div>
      </Card>
    );
  }

  const vars = explanationVariables(explanation, language);
  // Raw bundle strings: the `{name}` placeholders are filled here, not by i18next.
  const bundle = i18n.getResourceBundle(language, 'translation') as {
    explanation?: { summaries?: Record<string, string>; generic?: string };
  };
  const template = bundle.explanation?.summaries?.[explanation.rule_code];
  const generic = bundle.explanation?.generic;
  const summary =
    (template && fillTemplate(template, vars)) ??
    (generic && fillTemplate(generic, vars)) ??
    t('explanation.genericNoValues');

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Lightbulb className="size-4 text-warning" aria-hidden />
            {t('explanation.title')}
          </span>
        }
        description={t('explanation.runAt', { rule: explanation.rule_code })}
      />
      <div className="space-y-4 p-5">
        {explanation.parameter_status === 'PROVISIONAL' && (
          <InlineAlert tone="warning">{t('explanation.provisional')}</InlineAlert>
        )}
        <p className="text-[15px] leading-relaxed">{summary}</p>
        <ScoreScale explanation={explanation} />
        <div>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[13px] font-semibold text-info hover:underline"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            <ChevronRight className={open ? 'size-4 rotate-90 transition-transform' : 'size-4 transition-transform'} aria-hidden />
            {t('explanation.steps', { count: explanation.steps.length })}
          </button>
          {open && (
            <ol className="mt-3 space-y-3">
              {explanation.steps.map((step) => (
                <li key={step.step} className="rounded-md border border-border px-3 py-2">
                  <p className="text-[13px] font-semibold">
                    {step.step}. {step.text}
                  </p>
                  {Object.keys(step.details).length > 0 && (
                    <dl className="mt-1 grid grid-cols-1 gap-x-4 gap-y-0.5 font-mono text-xs text-muted sm:grid-cols-2">
                      {Object.entries(step.details).map(([key, value]) => (
                        <div key={key} className="flex min-w-0 gap-2">
                          <dt className="shrink-0">{key}</dt>
                          <dd className="truncate text-fg" title={JSON.stringify(value)}>
                            {typeof value === 'string' ? value : JSON.stringify(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </Card>
  );
}
