import { CheckCircle2, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { CUSTOMER_TYPES, PARAMETER_STATUSES, type CustomerType, type ParameterStatus, type Rule } from '@/api/schemas/rules';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { formatNumber } from '@/utils/format';
import { explainVars, isExplained, parameterDefault, type RuleValues } from './explain';

const STATUS_TONE: Record<ParameterStatus, 'neutral' | 'warning' | 'success'> = {
  UNSET: 'neutral',
  PROVISIONAL: 'warning',
  APPROVED: 'success',
};

function savedType(rule: Rule, type: CustomerType): { status: ParameterStatus; values: RuleValues } {
  const entry = (rule.thresholds as Record<string, { status?: unknown; values?: RuleValues } | undefined> | null)?.[type];
  const status = (PARAMETER_STATUSES as readonly unknown[]).includes(entry?.status) ? (entry!.status as ParameterStatus) : 'UNSET';
  return { status, values: entry?.values ?? {} };
}

/** One saved parameter value as text (E09 parameter list). */
const isUnset = (value: unknown) => value === null || value === undefined || value === '';

function parameterValueText(value: unknown, language: string): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.length === 0 ? '—' : value.map(String).join(', ');
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return '—';
    return entries.map(([key, item]) => `${formatNumber(item as string, language, { maximumFractionDigits: 6 })} ${key}`).join(', ');
  }
  if (typeof value === 'boolean') return String(value);
  return formatNumber(value as string, language, { maximumFractionDigits: 6 });
}

/** E09 — what the rule does, in a sentence built from its current parameters, with examples. */
export function RuleExplainer({ rule }: { rule: Rule }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  if (!rule.metadata || !isExplained(rule.rule_code)) return null;
  const code = rule.rule_code;
  const parameters = rule.metadata.parameters;
  // Dynamic per-rule keys; the typed key union is too large for TS to check here.
  const ruleText = (part: 'sentence' | 'yes' | 'no', vars: Record<string, string>) =>
    (t as unknown as (key: string, options: Record<string, string>) => string)(`ruleText.${code}.${part}`, vars);
  const context = {
    language,
    channel: (value: string) => t(`transactionsTable.channels.${value as 'atm'}`, { defaultValue: value }),
    status: (value: string) => t(`alertStatus.${value as 'new'}`, { defaultValue: value }),
  };

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
      {CUSTOMER_TYPES.map((type) => {
        const { status, values } = savedType(rule, type);
        const vars = status === 'UNSET' ? null : explainVars(code, values, context);
        return (
          <Card key={type} className="space-y-4 p-5" aria-label={`${t('ruleExplain.title')} · ${t(`rules.customerTypes.${type}`)}`} role="region">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold">
                {t('ruleExplain.title')} · {t(`rules.customerTypes.${type}`)}
              </h2>
              <Badge tone={STATUS_TONE[status]}>{t(`rules.statusShort.${status}`)}</Badge>
            </div>
            {status === 'UNSET' ? (
              <InlineAlert tone="info">{t('ruleExplain.unset')}</InlineAlert>
            ) : !vars ? (
              <InlineAlert tone="warning">{t('ruleExplain.incomplete')}</InlineAlert>
            ) : (
              <>
                <p className="text-[14px] leading-relaxed" data-testid={`rule-sentence-${type}`}>
                  {ruleText('sentence', vars)}
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-md border border-danger/30 bg-danger-soft p-3 text-[13px]">
                    <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-danger">
                      <CheckCircle2 className="size-3.5" aria-hidden />
                      {t('ruleExplain.triggers')}
                    </p>
                    <p>{ruleText('yes', vars)}</p>
                  </div>
                  <div className="rounded-md border border-border bg-surface-muted p-3 text-[13px]">
                    <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-muted">
                      <XCircle className="size-3.5" aria-hidden />
                      {t('ruleExplain.doesNotTrigger')}
                    </p>
                    <p>{ruleText('no', vars)}</p>
                  </div>
                </div>
                <p className="text-xs text-muted">{t('ruleExplain.exampleNote')}</p>
              </>
            )}
            {status !== 'UNSET' && (
              <div>
                <p className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">{t('ruleExplain.parameters')}</p>
                <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-[13px] sm:grid-cols-2">
                  {parameters.map((parameter) => (
                    <div key={parameter.name} className="flex min-w-0 justify-between gap-3 border-b border-border/60 pb-1" title={parameter.meaning}>
                      <dt className="truncate font-mono text-xs text-muted">{parameter.name}</dt>
                      <dd className="text-right font-medium tabular-nums">
                        {isUnset(values[parameter.name]) && parameterDefault(code, parameter.name) !== undefined ? (
                          <>
                            {parameterValueText(parameterDefault(code, parameter.name), language)}{' '}
                            <span className="text-xs font-normal text-muted">({t('ruleExplain.defaultValue')})</span>
                          </>
                        ) : (
                          parameterValueText(values[parameter.name], language)
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
