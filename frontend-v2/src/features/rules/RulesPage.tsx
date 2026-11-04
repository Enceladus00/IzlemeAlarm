import { AlertTriangle, ChevronDown, Lock } from 'lucide-react';
import { useMemo, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';
import { compareRuleCodes } from '@/api/schemas/alerts';
import { CUSTOMER_TYPES, PARAMETER_STATUSES, type CustomerType, type ParameterStatus, type Rule } from '@/api/schemas/rules';
import { REASON_MAX_LENGTH } from '@/api/schemas/rules';
import { useAuth } from '@/auth/auth-context';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Select';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { PageSpinner } from '@/components/ui/Spinner';
import { cn } from '@/utils/cn';
import { useRules, useUpdateRule } from './api';
import { buildRuleUpdate, copyIndividualToCorporate, draftFromRule, type DraftErrors, type RuleDraft } from './model';
import { ParameterFields } from './ParameterFields';
import { useFieldErrorText } from './useFieldErrorText';

const STATUS_TONE: Record<ParameterStatus, 'neutral' | 'warning' | 'success'> = {
  UNSET: 'neutral',
  PROVISIONAL: 'warning',
  APPROVED: 'success',
};

function typeStatus(rule: Rule, type: CustomerType): ParameterStatus {
  const entry = (rule.thresholds as Record<string, { status?: string } | undefined> | null)?.[type];
  return (PARAMETER_STATUSES as readonly string[]).includes(entry?.status ?? '') ? (entry!.status as ParameterStatus) : 'UNSET';
}

export default function RulesPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const rules = useRules();
  const editorRef = useRef<HTMLDivElement>(null);
  // On narrow screens the list sits above the editor; bring the editor into view.
  const selectRule = (code: string) => {
    setParams({ rule: code });
    if (window.matchMedia?.('(max-width: 1023px)').matches) {
      requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    }
  };

  const sorted = useMemo(() => [...(rules.data ?? [])].sort((a, b) => compareRuleCodes(a.rule_code, b.rule_code)), [rules.data]);
  const selected = sorted.find((rule) => rule.rule_code === params.get('rule')) ?? sorted[0];

  const header = <PageHeader breadcrumb={t('rules.breadcrumb')} title={t('nav.rules')} description={t('rules.description')} />;
  if (rules.isPending) return <PageSpinner label={t('common.loading')} />;
  if (rules.isError) {
    return (
      <>
        {header}
        <ErrorState error={rules.error} onRetry={() => void rules.refetch()} />
      </>
    );
  }
  if (!selected) {
    return (
      <>
        {header}
        <Card>
          <EmptyState title={t('rules.emptyRules')} />
        </Card>
      </>
    );
  }

  const registered = sorted.filter((rule) => rule.metadata);
  const legacy = sorted.filter((rule) => !rule.metadata);

  return (
    <>
      {header}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card className="h-fit p-2 lg:sticky lg:top-6">
          <nav aria-label={t('rules.listLabel')}>
            <RuleList rules={registered} selected={selected.rule_code} onSelect={selectRule} />
            {legacy.length > 0 && (
              <>
                <p className="mt-3 mb-1 px-3 text-[11px] font-medium tracking-wide text-muted uppercase">{t('rules.legacy')}</p>
                <RuleList rules={legacy} selected={selected.rule_code} onSelect={selectRule} />
              </>
            )}
          </nav>
        </Card>
        {/* Re-mount on rule change or fresh server data so the draft starts from saved values. */}
        <div ref={editorRef} className="min-w-0 scroll-mt-16">
          <RuleEditor key={`${selected.rule_code}-${rules.dataUpdatedAt}`} rule={selected} />
        </div>
      </div>
    </>
  );
}

function RuleList({ rules, selected, onSelect }: { rules: Rule[]; selected: string; onSelect: (code: string) => void }) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-0.5">
      {rules.map((rule) => {
        const current = rule.rule_code === selected;
        return (
          <li key={rule.rule_code}>
            <button
              type="button"
              onClick={() => onSelect(rule.rule_code)}
              aria-current={current ? 'true' : undefined}
              className={cn(
                'flex w-full items-start gap-3 rounded-md px-3 py-2 text-left text-[13px] hover:bg-surface-hover',
                current && 'bg-accent-soft ring-1 ring-accent/50',
              )}
            >
              <span className="w-9 shrink-0 font-mono font-semibold">{rule.rule_code}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate">{rule.name}</span>
                {rule.metadata && (
                  <span className="mt-1 flex gap-1">
                    {CUSTOMER_TYPES.map((type) => {
                      const status = typeStatus(rule, type);
                      return (
                        <span
                          key={type}
                          title={`${t(`rules.customerTypes.${type}`)}: ${t(`rules.statuses.${status}`)}`}
                          className={cn(
                            'rounded px-1 text-[10px] font-semibold',
                            status === 'APPROVED' ? 'bg-success-soft text-success' : status === 'PROVISIONAL' ? 'bg-warning-soft text-warning' : 'bg-neutral-soft text-muted',
                          )}
                        >
                          {type[0]}·{t(`rules.statusShort.${status}`)}
                        </span>
                      );
                    })}
                  </span>
                )}
              </span>
              <span
                className={cn('mt-1.5 size-2 shrink-0 rounded-full', rule.is_active ? 'bg-success' : 'bg-status-neutral/50')}
                title={rule.is_active ? t('rules.active') : t('rules.inactive')}
              >
                <span className="sr-only">{rule.is_active ? t('rules.active') : t('rules.inactive')}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function RuleEditor({ rule }: { rule: Rule }) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const canEdit = can('rule:edit');
  const initial = useMemo(() => draftFromRule(rule), [rule]);
  const [draft, setDraft] = useState<RuleDraft>(initial);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [guideOpen, setGuideOpen] = useState(false);
  const update = useUpdateRule();
  const errorText = useFieldErrorText();
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  if (!rule.metadata) {
    return (
      <Card className="space-y-4 p-5">
        <RuleHeading rule={rule} />
        <InlineAlert tone="info">
          <span className="inline-flex items-center gap-1.5">
            <Lock className="size-3.5" aria-hidden />
            {t('rules.legacyNotice')}
          </span>
        </InlineAlert>
        <div>
          <p className="mb-1 text-xs font-medium text-muted">{t('rules.legacyThresholds')}</p>
          <pre className="overflow-x-auto rounded-md bg-surface-muted p-3 font-mono text-xs">{JSON.stringify(rule.thresholds, null, 2)}</pre>
        </div>
      </Card>
    );
  }

  const metadata = rule.metadata;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const { errors: found, payload } = buildRuleUpdate(rule, draft);
    setErrors(found);
    if (payload) update.mutate({ code: rule.rule_code, body: payload });
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Card className="space-y-4 p-5">
        <RuleHeading rule={rule} />
        {!canEdit && <InlineAlert tone="info">{t('rules.readOnlyNotice')}</InlineAlert>}

        <div className="rounded-md border border-border">
          <button
            type="button"
            onClick={() => setGuideOpen((open) => !open)}
            aria-expanded={guideOpen}
            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-[13px] font-semibold"
          >
            {t('rules.guideTitle')}
            <ChevronDown className={cn('size-4 transition-transform', guideOpen && 'rotate-180')} aria-hidden />
          </button>
          {guideOpen && (
            <div className="space-y-4 border-t border-border px-4 py-4 text-[13px]">
              <p className="text-muted">
                {t('rules.feasibility', {
                  level: metadata.feasibility in { HIGH: 1, MEDIUM: 1, LOW: 1 } ? t(`rules.feasibilityLevels.${metadata.feasibility as 'HIGH'}`) : metadata.feasibility,
                })}{' '}
                {metadata.feasibility_reason}
              </p>
              {metadata.analyst_review_notes.map((note) => (
                <InlineAlert key={note} tone="warning">
                  {note}
                </InlineAlert>
              ))}
              <div>
                <p className="mb-1 font-semibold">{t('rules.steps')}</p>
                <ol className="list-decimal space-y-1 pl-5">
                  {metadata.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </div>
              <div>
                <p className="mb-1 font-semibold">{t('rules.parameterGuide')}</p>
                <ul className="space-y-1">
                  {metadata.parameters.map((parameter) => (
                    <li key={parameter.name}>
                      <span className="font-mono font-semibold">{parameter.name}</span> — {parameter.meaning}
                    </li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-muted">{t('rules.statusGuide')}</p>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="flex items-center gap-3 rounded-md border border-border-strong px-3 py-2.5 text-[13px] font-medium">
              <input
                type="checkbox"
                className="size-4 accent-[var(--accent)]"
                checked={draft.isActive}
                disabled={!canEdit}
                onChange={(event) => setDraft({ ...draft, isActive: event.target.checked })}
              />
              {t('rules.ruleActive')}
            </label>
            {errors.active && <p className="mt-1 text-xs font-medium text-danger">{t('rules.activeNeedsType')}</p>}
          </div>
          <Field label={t('rules.weight')} hint={t('rules.weightHint')} error={errorText(errors.weight)}>
            <Input
              type="number"
              inputMode="decimal"
              min={0}
              max={1}
              step={0.05}
              value={draft.weight}
              disabled={!canEdit}
              onChange={(event) => setDraft({ ...draft, weight: event.target.value })}
            />
          </Field>
        </div>
      </Card>

      {canEdit && (
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setDraft(copyIndividualToCorporate(draft))}
            title={t('rules.copyIndividualHint')}
          >
            {t('rules.copyIndividual')}
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
        {CUSTOMER_TYPES.map((type) => {
          const typeDraft = draft.types[type];
          return (
            <Card key={type} className="space-y-4 p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-semibold">{t(`rules.customerTypes.${type}`)}</h2>
                <Badge tone={STATUS_TONE[typeDraft.status]}>{t(`rules.statusShort.${typeDraft.status}`)}</Badge>
              </div>
              <Field label={`${t(`rules.customerTypes.${type}`)} · ${t('rules.parameterStatus')}`}>
                <Select
                  value={typeDraft.status}
                  disabled={!canEdit}
                  onChange={(event) =>
                    setDraft({ ...draft, types: { ...draft.types, [type]: { ...typeDraft, status: event.target.value as ParameterStatus } } })
                  }
                >
                  {PARAMETER_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {t(`rules.statuses.${status}`)}
                    </option>
                  ))}
                </Select>
              </Field>
              {typeDraft.status === 'UNSET' ? (
                <InlineAlert tone="info">{t('rules.unsetNotice')}</InlineAlert>
              ) : (
                <ParameterFields
                  rule={rule}
                  type={type}
                  draft={typeDraft}
                  errors={errors}
                  disabled={!canEdit}
                  onChange={(next) => setDraft({ ...draft, types: { ...draft.types, [type]: next } })}
                />
              )}
            </Card>
          );
        })}
      </div>

      {canEdit && (
        <Card className="p-5">
          <Field
            label={
              <>
                {t('rules.reason')}
                <span className="text-danger"> *</span>
              </>
            }
            hint={t('rules.reasonHint', { count: draft.reason.length, max: REASON_MAX_LENGTH })}
            error={errorText(errors.reason)}
          >
            <Textarea
              rows={2}
              maxLength={REASON_MAX_LENGTH}
              value={draft.reason}
              onChange={(event) => setDraft({ ...draft, reason: event.target.value })}
            />
          </Field>
        </Card>
      )}

      {canEdit && (
        <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface/95 px-4 py-3 shadow-lg backdrop-blur">
          <Button type="submit" variant="primary" loading={update.isPending}>
            {t('rules.save')}
          </Button>
          {dirty && (
            <>
              <span className="text-xs text-muted">{t('rules.unsavedChanges')}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft(initial);
                  setErrors({});
                  update.reset();
                }}
              >
                {t('rules.discard')}
              </Button>
            </>
          )}
          <div className="w-full empty:hidden" aria-live="polite">
            {Object.keys(errors).length > 0 && (
              <p className="flex items-center gap-1.5 text-xs font-medium text-danger">
                <AlertTriangle className="size-3.5" aria-hidden />
                {t('rules.fixErrors')}
              </p>
            )}
            {update.isError && <ErrorState error={update.error} title={t('errors.validation')} />}
            {update.isSuccess && !dirty && <InlineAlert tone="success">{t('rules.saved', { code: rule.rule_code })}</InlineAlert>}
          </div>
        </div>
      )}
    </form>
  );
}

function RuleHeading({ rule }: { rule: Rule }) {
  const { t } = useTranslation();
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-bold">
          <span className="font-mono">{rule.rule_code}</span> — {rule.name}
        </h2>
        <Badge tone={rule.is_active ? 'success' : 'neutral'} dot>
          {rule.is_active ? t('rules.active') : t('rules.inactive')}
        </Badge>
        {rule.metadata?.alert_mode === 'SIGNAL_ONLY' && <Badge tone="neutral">{t('rules.signalOnly')}</Badge>}
      </div>
      {rule.description && <p className="mt-1 text-[13px] text-muted">{rule.description}</p>}
    </div>
  );
}
