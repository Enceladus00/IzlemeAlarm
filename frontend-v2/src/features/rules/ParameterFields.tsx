import { Plus } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { CustomerType, Rule, RuleParameter } from '@/api/schemas/rules';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { Select, Textarea } from '@/components/ui/Select';
import {
  BOUNDS,
  CASH_CHANNELS,
  OPEN_STATUSES,
  SPECIAL_NAMES,
  hasParam,
  integerAnchors,
  type DraftErrors,
  type TypeDraft,
} from './model';
import { useFieldErrorText } from './useFieldErrorText';

function NumberField({
  label,
  hint,
  value,
  onChange,
  error,
  disabled,
  integer,
  min,
  max,
}: {
  label: ReactNode;
  hint?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  disabled: boolean;
  integer?: boolean;
  min?: number | null;
  max?: number | null;
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      <Input
        type="number"
        inputMode={integer ? 'numeric' : 'decimal'}
        step={integer ? 1 : 'any'}
        min={min ?? undefined}
        max={max ?? undefined}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

/** Inputs for one customer type, following the field kinds in model.ts. */
export function ParameterFields({
  rule,
  type,
  draft,
  onChange,
  errors,
  disabled,
}: {
  rule: Rule;
  type: CustomerType;
  draft: TypeDraft;
  onChange: (next: TypeDraft) => void;
  errors: DraftErrors;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const errorText = useFieldErrorText();
  const parameters: RuleParameter[] = rule.metadata?.parameters ?? [];
  const byName = new Map(parameters.map((parameter) => [parameter.name, parameter]));
  const err = (field: string) => errorText(errors[`${type}.${field}`]);
  const setNumber = (name: string, value: string) => onChange({ ...draft, numbers: { ...draft.numbers, [name]: value } });
  const integer = integerAnchors(parameters);

  return (
    <div className="space-y-4">
      {hasParam(parameters, 'limits') && (
        <fieldset className="space-y-2">
          <legend className="text-[13px] font-semibold">{t('rules.limitsTitle')}</legend>
          <p className="text-xs text-muted">{t('rules.limitsHint')}</p>
          {draft.limits.map((row, index) => {
            const rowError = err(`limits.${index}`);
            return (
              <div key={index}>
                <div className="grid grid-cols-[96px_1fr] gap-2">
                  <Input
                    aria-label={`${t('rules.currencyCode')} ${index + 1}`}
                    value={row.currency}
                    maxLength={3}
                    disabled={disabled}
                    aria-invalid={rowError ? true : undefined}
                    className="font-mono uppercase"
                    onChange={(event) => {
                      const limits = [...draft.limits];
                      limits[index] = { ...row, currency: event.target.value.toUpperCase() };
                      onChange({ ...draft, limits });
                    }}
                  />
                  <Input
                    aria-label={`${t('rules.referenceAmount')} ${index + 1}`}
                    type="number"
                    inputMode="decimal"
                    step="any"
                    min={0}
                    value={row.amount}
                    disabled={disabled}
                    aria-invalid={rowError ? true : undefined}
                    onChange={(event) => {
                      const limits = [...draft.limits];
                      limits[index] = { ...row, amount: event.target.value };
                      onChange({ ...draft, limits });
                    }}
                  />
                </div>
                {rowError && <p className="mt-1 text-xs font-medium text-danger">{rowError}</p>}
              </div>
            );
          })}
          {err('limits') && <p className="text-xs font-medium text-danger">{err('limits')}</p>}
          {!disabled && (
            <Button size="sm" variant="ghost" onClick={() => onChange({ ...draft, limits: [...draft.limits, { currency: '', amount: '' }] })}>
              <Plus className="size-3.5" aria-hidden />
              {t('rules.addLimitRow')}
            </Button>
          )}
        </fieldset>
      )}

      {hasParam(parameters, 'window_days') && (
        <NumberField
          label={t('rules.windowDays')}
          hint={t('rules.windowDaysHint')}
          value={draft.numbers.window_days ?? ''}
          onChange={(value) => setNumber('window_days', value)}
          error={err('window_days')}
          disabled={disabled}
          integer
          min={1}
        />
      )}

      {hasParam(parameters, 'x_esik') && hasParam(parameters, 'x_kesin') && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <NumberField
            label={t('rules.xEsik', { unit: byName.get('x_esik')!.unit })}
            hint={byName.get('x_esik')!.meaning}
            value={draft.numbers.x_esik ?? ''}
            onChange={(value) => setNumber('x_esik', value)}
            error={err('x_esik')}
            disabled={disabled}
            integer={integer}
            min={0}
          />
          <NumberField
            label={t('rules.xKesin', { unit: byName.get('x_kesin')!.unit })}
            hint={byName.get('x_kesin')!.meaning}
            value={draft.numbers.x_kesin ?? ''}
            onChange={(value) => setNumber('x_kesin', value)}
            error={err('x_kesin')}
            disabled={disabled}
            integer={integer}
            min={integer ? 1 : 0.0001}
          />
        </div>
      )}

      {rule.rule_code === 'R01' && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <NumberField
              label={t('rules.bandLow')}
              hint={t('rules.bandLowHint')}
              value={draft.numbers.band_low ?? ''}
              onChange={(value) => setNumber('band_low', value)}
              error={err('band_low')}
              disabled={disabled}
              min={0.0001}
              max={0.9999}
            />
            <NumberField
              label={t('rules.aboveCheck')}
              hint={t('rules.aboveCheckHint')}
              value={draft.numbers.above_check ?? ''}
              onChange={(value) => setNumber('above_check', value)}
              error={err('above_check')}
              disabled={disabled}
              min={1.0001}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <NumberField
              label={t('rules.incomeRatio')}
              hint={t('rules.incomeRatioHint')}
              value={draft.numbers.minimum_income_ratio ?? ''}
              onChange={(value) => setNumber('minimum_income_ratio', value)}
              error={err('minimum_income_ratio')}
              disabled={disabled}
              min={0.0001}
            />
            <Field label={t('rules.incomeCurrency')} hint={t('rules.incomeCurrencyHint')} error={err('income_currency')}>
              <Input
                value={draft.incomeCurrency}
                maxLength={3}
                disabled={disabled}
                className="font-mono uppercase"
                onChange={(event) => onChange({ ...draft, incomeCurrency: event.target.value.toUpperCase() })}
              />
            </Field>
          </div>
        </>
      )}

      {hasParam(parameters, 'cash_channels') && (
        <fieldset>
          <legend className="text-[13px] font-medium">{t('rules.cashChannels')}</legend>
          <p className="mb-2 text-xs text-muted">{t('rules.cashChannelsHint')}</p>
          <div className="flex flex-wrap gap-2">
            {CASH_CHANNELS.map((channel) => {
              const checked = draft.cashChannels.includes(channel);
              return (
                <label
                  key={channel}
                  className="flex items-center gap-2 rounded-md border border-border-strong px-3 py-1.5 text-[13px] has-[:checked]:border-accent has-[:checked]:bg-accent-soft"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-[var(--accent)]"
                    checked={checked}
                    disabled={disabled}
                    onChange={() =>
                      onChange({
                        ...draft,
                        cashChannels: checked ? draft.cashChannels.filter((c) => c !== channel) : [...draft.cashChannels, channel],
                      })
                    }
                  />
                  {t(`transactionsTable.channels.${channel}`)}
                </label>
              );
            })}
          </div>
          {err('cash_channels') && <p className="mt-1 text-xs font-medium text-danger">{err('cash_channels')}</p>}
        </fieldset>
      )}

      {hasParam(parameters, 'cash_accounts') && (
        <Field label={t('rules.cashAccounts')} hint={t('rules.cashAccountsHint')} error={err('cash_accounts')}>
          <Textarea
            rows={2}
            className="min-h-0 font-mono"
            value={draft.cashAccounts}
            disabled={disabled}
            onChange={(event) => onChange({ ...draft, cashAccounts: event.target.value })}
          />
        </Field>
      )}

      {hasParam(parameters, 'season_factor') && (
        <Field label={t('rules.seasonFactor')} hint={t('rules.seasonFactorHint')} error={err('season_factor')}>
          <Textarea
            rows={3}
            className="min-h-0 font-mono"
            value={draft.seasonFactor}
            disabled={disabled}
            onChange={(event) => onChange({ ...draft, seasonFactor: event.target.value })}
          />
        </Field>
      )}

      {hasParam(parameters, 'suspicious_status') && (
        <Field label={t('rules.suspiciousStatus')} hint={t('rules.suspiciousStatusHint')}>
          <Select value={draft.suspiciousStatus} disabled={disabled} onChange={(event) => onChange({ ...draft, suspiciousStatus: event.target.value })}>
            <option value="confirmed_suspicious">{t('alertStatus.confirmed_suspicious')}</option>
          </Select>
        </Field>
      )}

      {hasParam(parameters, 'countries') && (
        <Field label={t('rules.countries')} hint={t('rules.countriesHint')} error={err('countries')}>
          <Input
            className="font-mono"
            value={draft.countries}
            disabled={disabled}
            onChange={(event) => onChange({ ...draft, countries: event.target.value })}
          />
        </Field>
      )}

      {hasParam(parameters, 'excluded_rules') && (
        <Field label={t('rules.excludedRules')} hint={t('rules.excludedRulesHint')} error={err('excluded_rules')}>
          <Input
            className="font-mono"
            value={draft.excludedRules}
            disabled={disabled}
            onChange={(event) => onChange({ ...draft, excludedRules: event.target.value })}
          />
        </Field>
      )}

      {hasParam(parameters, 'open_statuses') && (
        <fieldset>
          <legend className="text-[13px] font-semibold">{t('rules.openStatuses')}</legend>
          <div className="mt-2 flex flex-wrap gap-4">
            {OPEN_STATUSES.map((status) => (
              <label key={status} className="flex items-center gap-2 text-[13px]">
                <input
                  type="checkbox"
                  className="size-4 accent-[var(--accent)]"
                  checked={draft.openStatuses.includes(status)}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      openStatuses: event.target.checked
                        ? [...draft.openStatuses, status]
                        : draft.openStatuses.filter((item) => item !== status),
                    })
                  }
                />
                {t(`alertStatus.${status}`)}
              </label>
            ))}
          </div>
          {err('open_statuses') && <p className="mt-1 text-xs font-medium text-danger">{err('open_statuses')}</p>}
        </fieldset>
      )}

      {parameters
        .filter((parameter) => !SPECIAL_NAMES.has(parameter.name))
        .map((parameter) => {
          const [min, max] = BOUNDS[parameter.name] ?? [null, null];
          return (
            <NumberField
              key={parameter.name}
              label={
                <>
                  <span className="font-mono">{parameter.name}</span> <span className="font-normal text-muted">({parameter.unit})</span>
                </>
              }
              hint={parameter.meaning}
              value={draft.numbers[parameter.name] ?? ''}
              onChange={(value) => setNumber(parameter.name, value)}
              error={err(parameter.name)}
              disabled={disabled}
              integer={parameter.type === 'integer'}
              min={min}
              max={max}
            />
          );
        })}
    </div>
  );
}
