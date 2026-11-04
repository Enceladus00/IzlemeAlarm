/**
 * Form model for rule parameters. Field kinds, defaults, bounds and
 * validation mirror frontend/app_pages/rule_management.py; the API remains
 * the authoritative validator (backend/detection/parameters.py).
 */
import {
  CUSTOMER_TYPES,
  PARAMETER_STATUSES,
  REASON_MAX_LENGTH,
  type CustomerType,
  type ParameterStatus,
  type Rule,
  type RuleParameter,
  type RuleUpdate,
} from '@/api/schemas/rules';

export const CASH_CHANNELS = ['atm', 'mobile', 'internet', 'branch'] as const;

/** Inclusive numeric bounds for generic parameters (same table as Streamlit). */
export const BOUNDS: Record<string, [number | null, number | null]> = {
  history_days: [1, null],
  history_weeks: [1, null],
  min_count: [1, null],
  income_bands: [2, null],
  dormant_days: [1, null],
  account_age_days: [1, null],
  baseline_days: [1, null],
  window_hours: [1, null],
  max_step_hours: [1, null],
  max_depth: [2, 20],
  max_cycle_length: [3, 20],
  ratio_low: [0, null],
  ratio_high: [0.000001, null],
  kappa: [0, null],
  mad_floor: [0.000001, null],
  cv_threshold: [0.000001, null],
  cv_multiplier: [0.000001, null],
  decay_low: [0.000001, 0.999999],
  decay_high: [0.000001, 0.999999],
  min_retained: [0, 1],
  pingpong_tolerance: [0, null],
  gamma: [0, 1],
  round_unit: [0.000001, null],
  min_rules: [2, null],
  p: [1, null],
  alert_threshold: [0.000001, 1],
};

/** Rules whose x_esik / x_kesin are shares between 0 and 1. */
export const RATIO_ANCHOR_RULES = new Set(['S1']);
export const OPEN_STATUSES = ['new', 'in_review'] as const;

/** Names with dedicated inputs; everything else is a bounded number. */
export const SPECIAL_NAMES = new Set([
  'limits',
  'x_esik',
  'x_kesin',
  'window_days',
  'band_low',
  'above_check',
  'minimum_income_ratio',
  'income_currency',
  'cash_channels',
  'cash_accounts',
  'season_factor',
  'suspicious_status',
  'countries',
  'excluded_rules',
  'open_statuses',
]);

export interface LimitRow {
  currency: string;
  amount: string;
}

/** Every value is kept as text while editing; conversion happens on save. */
export interface TypeDraft {
  status: ParameterStatus;
  limits: LimitRow[];
  numbers: Record<string, string>;
  incomeCurrency: string;
  cashChannels: string[];
  cashAccounts: string;
  seasonFactor: string;
  suspiciousStatus: string;
  /** R16: comma-separated ISO country codes. */
  countries: string;
  /** R17: comma-separated rule codes. */
  excludedRules: string;
  openStatuses: string[];
}

export interface RuleDraft {
  isActive: boolean;
  weight: string;
  types: Record<CustomerType, TypeDraft>;
  /** K5: required reason for the change. */
  reason: string;
}

export type FieldError =
  | { key: 'limitCurrencyMissing'; row: number }
  | { key: 'limitCurrencyInvalid'; row: number }
  | { key: 'limitDuplicate'; currency: string }
  | { key: 'limitAmount'; currency: string }
  | { key: 'limitsRequired' }
  | { key: 'required' }
  | { key: 'min'; min: number }
  | { key: 'max'; max: number }
  | { key: 'integer' }
  | { key: 'anchorsOrder' }
  | { key: 'currencyCode' }
  | { key: 'channelsRequired' }
  | { key: 'cashAccounts' }
  | { key: 'cashAccountsUnique' }
  | { key: 'seasonFactor' }
  | { key: 'countries' }
  | { key: 'ruleCodes' }
  | { key: 'statusesRequired' }
  | { key: 'reasonRequired' }
  | { key: 'reasonTooLong'; max: number };

/** Errors keyed by "<customerType>.<field>" or "weight"/"active". */
export type DraftErrors = Record<string, FieldError>;

export function hasParam(parameters: RuleParameter[], name: string): boolean {
  return parameters.some((parameter) => parameter.name === name);
}

export function integerAnchors(parameters: RuleParameter[]): boolean {
  const byName = new Map(parameters.map((parameter) => [parameter.name, parameter]));
  return byName.get('x_esik')?.type === 'integer' && byName.get('x_kesin')?.type === 'integer';
}

function text(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

function asStatus(value: unknown): ParameterStatus {
  return (PARAMETER_STATUSES as readonly unknown[]).includes(value) ? (value as ParameterStatus) : 'UNSET';
}

/** Builds the editable draft from saved thresholds (no production values are invented). */
export function draftFromRule(rule: Rule): RuleDraft {
  const parameters = rule.metadata?.parameters ?? [];
  const thresholds = (rule.thresholds ?? {}) as Record<string, { status?: unknown; values?: Record<string, unknown> } | undefined>;
  const types = {} as Record<CustomerType, TypeDraft>;
  for (const type of CUSTOMER_TYPES) {
    const saved = thresholds[type];
    const values = saved?.values ?? {};
    const limits = Object.entries((values.limits as Record<string, unknown>) ?? {})
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([currency, amount]) => ({ currency, amount: text(amount) }));
    const numbers: Record<string, string> = {};
    for (const parameter of parameters) {
      if (
        parameter.name === 'limits' ||
        ['income_currency', 'cash_channels', 'cash_accounts', 'season_factor', 'suspicious_status', 'countries', 'excluded_rules', 'open_statuses'].includes(
          parameter.name,
        )
      ) {
        continue;
      }
      numbers[parameter.name] = text(values[parameter.name]);
    }
    // Streamlit defaults: a 7-day window and the R01 band/upper-check ratios.
    if (hasParam(parameters, 'window_days') && numbers.window_days === '') numbers.window_days = '7';
    if (rule.rule_code === 'R01') {
      if (numbers.band_low === '') numbers.band_low = '0.9';
      if (numbers.above_check === '') numbers.above_check = '1.1';
    }
    types[type] = {
      status: asStatus(saved?.status),
      limits: [...limits, ...Array.from({ length: Math.max(3, limits.length + 1) - limits.length }, () => ({ currency: '', amount: '' }))],
      numbers,
      incomeCurrency: text(values.income_currency),
      cashChannels: Array.isArray(values.cash_channels) ? values.cash_channels.map(String).filter((c) => (CASH_CHANNELS as readonly string[]).includes(c)) : [],
      cashAccounts: Array.isArray(values.cash_accounts) ? values.cash_accounts.join(', ') : '',
      seasonFactor: Object.entries((values.season_factor as Record<string, unknown>) ?? {})
        .map(([date, factor]) => `${date}=${text(factor)}`)
        .join('\n'),
      suspiciousStatus: 'confirmed_suspicious',
      countries: Array.isArray(values.countries) ? values.countries.join(', ') : '',
      excludedRules: Array.isArray(values.excluded_rules)
        ? values.excluded_rules.join(', ')
        : hasParam(parameters, 'excluded_rules')
          ? 'R02, R17, R18'
          : '',
      openStatuses: Array.isArray(values.open_statuses)
        ? values.open_statuses.map(String).filter((s) => (OPEN_STATUSES as readonly string[]).includes(s))
        : [...OPEN_STATUSES],
    };
  }
  return { isActive: rule.is_active, weight: text(rule.weight ?? '0'), types, reason: '' };
}

function parseNumber(raw: string): number | null {
  if (raw.trim() === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : NaN;
}

function checkNumber(
  raw: string,
  { min, max, integer }: { min: number | null; max: number | null; integer: boolean },
): { value: number | null; error?: FieldError } {
  const value = parseNumber(raw);
  if (value === null) return { value: null, error: { key: 'required' } };
  if (Number.isNaN(value)) return { value: null, error: { key: 'required' } };
  if (integer && !Number.isInteger(value)) return { value: null, error: { key: 'integer' } };
  if (min !== null && value < min) return { value: null, error: { key: 'min', min } };
  if (max !== null && value > max) return { value: null, error: { key: 'max', max } };
  return { value };
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Validates one customer type and returns API-ready values (or errors). */
function buildTypeValues(
  ruleCode: string,
  parameters: RuleParameter[],
  type: CustomerType,
  draft: TypeDraft,
  errors: DraftErrors,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  const fail = (field: string, error: FieldError) => {
    errors[`${type}.${field}`] ??= error;
  };
  const names = new Set(parameters.map((parameter) => parameter.name));

  if (names.has('limits')) {
    const limits: Record<string, number> = {};
    let invalid = false;
    draft.limits.forEach((row, index) => {
      const currency = row.currency.trim().toUpperCase();
      const amount = parseNumber(row.amount);
      if (!currency && (amount === null || amount === 0)) return;
      if (!currency) {
        fail(`limits.${index}`, { key: 'limitCurrencyMissing', row: index + 1 });
        invalid = true;
      } else if (!/^[A-Z]{3}$/.test(currency)) {
        fail(`limits.${index}`, { key: 'limitCurrencyInvalid', row: index + 1 });
        invalid = true;
      } else if (currency in limits) {
        fail(`limits.${index}`, { key: 'limitDuplicate', currency });
        invalid = true;
      } else if (amount === null || Number.isNaN(amount) || amount <= 0) {
        fail(`limits.${index}`, { key: 'limitAmount', currency });
        invalid = true;
      } else {
        limits[currency] = amount;
      }
    });
    if (!invalid && Object.keys(limits).length === 0) fail('limits', { key: 'limitsRequired' });
    values.limits = limits;
  }

  if (names.has('window_days')) {
    const { value, error } = checkNumber(draft.numbers.window_days ?? '', { min: 1, max: null, integer: true });
    if (error) fail('window_days', error);
    values.window_days = value;
  }

  if (names.has('x_esik') && names.has('x_kesin')) {
    const integer = integerAnchors(parameters);
    const ratio = RATIO_ANCHOR_RULES.has(ruleCode);
    const esik = checkNumber(draft.numbers.x_esik ?? '', { min: 0, max: ratio ? 1 : null, integer });
    const kesin = checkNumber(draft.numbers.x_kesin ?? '', { min: integer ? 1 : 0.0001, max: ratio ? 1 : null, integer });
    if (esik.error) fail('x_esik', esik.error);
    if (kesin.error) fail('x_kesin', kesin.error);
    if (!esik.error && !kesin.error && kesin.value! <= esik.value!) fail('x_kesin', { key: 'anchorsOrder' });
    values.x_esik = esik.value;
    values.x_kesin = kesin.value;
  }

  if (ruleCode === 'R01') {
    const band = checkNumber(draft.numbers.band_low ?? '', { min: 0.0001, max: 0.9999, integer: false });
    const above = checkNumber(draft.numbers.above_check ?? '', { min: 1.0001, max: null, integer: false });
    const ratio = checkNumber(draft.numbers.minimum_income_ratio ?? '', { min: 0.0001, max: null, integer: false });
    if (band.error) fail('band_low', band.error);
    if (above.error) fail('above_check', above.error);
    if (ratio.error) fail('minimum_income_ratio', ratio.error);
    const currency = draft.incomeCurrency.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(currency)) fail('income_currency', { key: 'currencyCode' });
    Object.assign(values, {
      band_low: band.value,
      above_check: above.value,
      minimum_income_ratio: ratio.value,
      income_currency: currency,
    });
  }

  if (names.has('cash_channels')) {
    if (draft.cashChannels.length === 0) fail('cash_channels', { key: 'channelsRequired' });
    values.cash_channels = [...draft.cashChannels];
  }

  if (names.has('cash_accounts')) {
    const parts = draft.cashAccounts.split(',').map((part) => part.trim()).filter(Boolean);
    const ids = parts.map(Number);
    if (ids.some((id) => !Number.isInteger(id) || id <= 0)) fail('cash_accounts', { key: 'cashAccounts' });
    else if (new Set(ids).size !== ids.length) fail('cash_accounts', { key: 'cashAccountsUnique' });
    values.cash_accounts = ids;
  }

  if (names.has('season_factor')) {
    const factors: Record<string, string> = {};
    for (const line of draft.seasonFactor.split('\n')) {
      if (!line.trim()) continue;
      const [datePart, factorPart] = line.split('=', 2);
      const date = datePart?.trim() ?? '';
      const factor = Number(factorPart?.trim());
      const parsed = new Date(`${date}T00:00:00`);
      const validDate = ISO_DATE.test(date) && !Number.isNaN(parsed.getTime()) && date === `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, '0')}-${String(parsed.getDate()).padStart(2, '0')}`;
      if (!validDate || factorPart === undefined || !Number.isFinite(factor) || factor <= 0 || date in factors) {
        fail('season_factor', { key: 'seasonFactor' });
        break;
      }
      factors[date] = factorPart.trim();
    }
    values.season_factor = factors;
  }

  if (names.has('suspicious_status')) values.suspicious_status = draft.suspiciousStatus;

  if (names.has('countries')) {
    const codes = draft.countries.split(',').map((part) => part.trim().toUpperCase()).filter(Boolean);
    if (codes.length === 0 || codes.some((code) => !/^[A-Z]{2}$/.test(code)) || new Set(codes).size !== codes.length) {
      fail('countries', { key: 'countries' });
    }
    values.countries = codes;
  }

  if (names.has('excluded_rules')) {
    const codes = draft.excludedRules.split(',').map((part) => part.trim().toUpperCase()).filter(Boolean);
    if (codes.some((code) => !/^(R\d{1,2}|S\d)$/.test(code)) || new Set(codes).size !== codes.length) {
      fail('excluded_rules', { key: 'ruleCodes' });
    }
    values.excluded_rules = codes;
  }

  if (names.has('open_statuses')) {
    if (draft.openStatuses.length === 0) fail('open_statuses', { key: 'statusesRequired' });
    values.open_statuses = OPEN_STATUSES.filter((status) => draft.openStatuses.includes(status));
  }

  for (const parameter of parameters) {
    if (SPECIAL_NAMES.has(parameter.name)) continue;
    const [min, max] = BOUNDS[parameter.name] ?? [null, null];
    const { value, error } = checkNumber(draft.numbers[parameter.name] ?? '', { min, max, integer: parameter.type === 'integer' });
    if (error) fail(parameter.name, error);
    values[parameter.name] = value;
  }
  return values;
}

/** Validates the whole draft; returns the PUT body only when there are no errors. */
export function buildRuleUpdate(rule: Rule, draft: RuleDraft): { errors: DraftErrors; payload: RuleUpdate | null } {
  const parameters = rule.metadata?.parameters ?? [];
  const errors: DraftErrors = {};
  const thresholds = {} as RuleUpdate['thresholds'];
  for (const type of CUSTOMER_TYPES) {
    const typeDraft = draft.types[type];
    thresholds[type] =
      typeDraft.status === 'UNSET'
        ? { status: 'UNSET', values: {} }
        : { status: typeDraft.status, values: buildTypeValues(rule.rule_code, parameters, type, typeDraft, errors) };
  }
  const weight = checkNumber(draft.weight, { min: 0, max: 1, integer: false });
  if (weight.error) errors.weight = weight.error;
  if (draft.isActive && CUSTOMER_TYPES.every((type) => draft.types[type].status === 'UNSET')) {
    errors.active = { key: 'required' };
  }
  const reason = draft.reason.trim();
  if (!reason) errors.reason = { key: 'reasonRequired' };
  else if (reason.length > REASON_MAX_LENGTH) errors.reason = { key: 'reasonTooLong', max: REASON_MAX_LENGTH };
  if (Object.keys(errors).length > 0) return { errors, payload: null };
  return { errors, payload: { is_active: draft.isActive, weight: weight.value!, thresholds, reason } };
}

/** K11: copy the individual (BIREYSEL) settings to corporate (KURUMSAL). */
export function copyIndividualToCorporate(draft: RuleDraft): RuleDraft {
  const source = draft.types.BIREYSEL;
  return {
    ...draft,
    types: {
      ...draft.types,
      KURUMSAL: {
        ...source,
        limits: source.limits.map((row) => ({ ...row })),
        numbers: { ...source.numbers },
        cashChannels: [...source.cashChannels],
        openStatuses: [...source.openStatuses],
      },
    },
  };
}
